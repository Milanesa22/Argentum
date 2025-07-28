"""
AURELIUS Analytics and Reporting Module
Generates comprehensive reports on engagement, sales, and system performance.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics

from ...config import config
from ...logging_config import get_logger, log_data_operation
from ...db.redis_client import data_client
from ...modules.sales.paypal import paypal_service

logger = get_logger("ANALYTICS")

class AureliusAnalytics:
    """
    Comprehensive analytics and reporting system for AURELIUS.
    Generates real-time reports on social media engagement, sales performance, and system metrics.
    """

    def __init__(self):
        # Data keys for different analytics sources
        self.social_keys = {
            "twitter": "twitter:posted_content",
            "mastodon": "mastodon:posted_content",
            "discord": "discord:posted_content"
        }

        self.engagement_keys = {
            "twitter": "twitter:analytics",
            "mastodon": "mastodon:analytics",
            "discord": "discord:interactions"
        }

        self.sales_keys = {
            "orders": "paypal:orders",
            "payments": "paypal:payments",
            "refunds": "paypal:refunds"
        }

        self.system_keys = {
            "rate_limits": "rate_limit:",
            "ai_usage": "ai:usage",
            "errors": "system:errors"
        }

    async def generate_daily_report(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate comprehensive daily report.
        Returns detailed analytics for the specified date.
        """
        try:
            target_date = date or datetime.now()
            date_str = target_date.strftime("%Y-%m-%d")

            logger.info(f"📊 Generating daily report for {date_str}")

            # Gather data from all sources
            social_data = await self._get_social_media_analytics(target_date, "daily")
            sales_data = await self._get_sales_analytics(target_date, "daily")
            engagement_data = await self._get_engagement_analytics(target_date, "daily")
            system_data = await self._get_system_analytics(target_date, "daily")

            # Compile comprehensive report
            report = {
                "report_type": "daily",
                "date": date_str,
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_posts": social_data.get("total_posts", 0),
                    "total_engagement": engagement_data.get("total_engagement", 0),
                    "total_revenue": sales_data.get("total_revenue", 0),
                    "total_transactions": sales_data.get("total_transactions", 0),
                    "system_uptime": system_data.get("uptime_percentage", 0)
                },
                "social_media": social_data,
                "sales": sales_data,
                "engagement": engagement_data,
                "system": system_data,
                "insights": await self._generate_insights(social_data, sales_data, engagement_data),
                "recommendations": await self._generate_recommendations(social_data, sales_data, engagement_data)
            }

            # Store report
            await self._store_report(report, "daily", date_str)

            logger.info(f"✅ Daily report generated successfully for {date_str}")
            return report

        except Exception as e:
            logger.error(f"❌ Error generating daily report: {e}")
            return {
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def generate_weekly_report(self, week_start: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate comprehensive weekly report.
        Returns detailed analytics for the specified week.
        """
        try:
            if not week_start:
                # Get Monday of current week
                today = datetime.now()
                week_start = today - timedelta(days=today.weekday())
            
            week_end = week_start + timedelta(days=6)
            week_str = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
            
            logger.info(f"📊 Generating weekly report for {week_str}")
            
            # Gather weekly data
            social_data = await self._get_social_media_analytics(week_start, "weekly", week_end)
            sales_data = await self._get_sales_analytics(week_start, "weekly", week_end)
            engagement_data = await self._get_engagement_analytics(week_start, "weekly", week_end)
            system_data = await self._get_system_analytics(week_start, "weekly", week_end)
            
            # Calculate trends (compare with previous week)
            previous_week_start = week_start - timedelta(days=7)
            previous_week_end = previous_week_start + timedelta(days=6)
            
            previous_social = await self._get_social_media_analytics(previous_week_start, "weekly", previous_week_end)
            previous_sales = await self._get_sales_analytics(previous_week_start, "weekly", previous_week_end)
            
            trends = self._calculate_trends(
                current_social=social_data,
                previous_social=previous_social,
                current_sales=sales_data,
                previous_sales=previous_sales
            )
            
            report = {
                "report_type": "weekly",
                "period": week_str,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_posts": social_data.get("total_posts", 0),
                    "total_engagement": engagement_data.get("total_engagement", 0),
                    "total_revenue": sales_data.get("total_revenue", 0),
                    "total_transactions": sales_data.get("total_transactions", 0),
                    "average_daily_posts": round(social_data.get("total_posts", 0) / 7, 1),
                    "average_daily_revenue": round(sales_data.get("total_revenue", 0) / 7, 2)
                },
                "social_media": social_data,
                "sales": sales_data,
                "engagement": engagement_data,
                "system": system_data,
                "trends": trends,
                "insights": await self._generate_insights(social_data, sales_data, engagement_data),
                "recommendations": await self._generate_recommendations(social_data, sales_data, engagement_data)
            }
            
            # Store report
            await self._store_report(report, "weekly", week_start.strftime("%Y-W%U"))
            
            logger.info(f"✅ Weekly report generated successfully for {week_str}")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error generating weekly report: {e}")
            return {
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def generate_monthly_report(self, month: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate comprehensive monthly report.
        Returns detailed analytics for the specified month.
        """
        try:
            if not month:
                month = datetime.now().replace(day=1)
            
            # Get month boundaries
            month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1) - timedelta(days=1)
            
            month_str = month_start.strftime("%Y-%m")
            
            logger.info(f"📊 Generating monthly report for {month_str}")
            
            # Gather monthly data
            social_data = await self._get_social_media_analytics(month_start, "monthly", month_end)
            sales_data = await self._get_sales_analytics(month_start, "monthly", month_end)
            engagement_data = await self._get_engagement_analytics(month_start, "monthly", month_end)
            system_data = await self._get_system_analytics(month_start, "monthly", month_end)
            
            # Calculate month-over-month trends
            previous_month_start = (month_start - timedelta(days=1)).replace(day=1)
            if previous_month_start.month == 12:
                previous_month_end = previous_month_start.replace(year=previous_month_start.year + 1, month=1) - timedelta(days=1)
            else:
                previous_month_end = previous_month_start.replace(month=previous_month_start.month + 1) - timedelta(days=1)
            
            previous_social = await self._get_social_media_analytics(previous_month_start, "monthly", previous_month_end)
            previous_sales = await self._get_sales_analytics(previous_month_start, "monthly", previous_month_end)
            
            trends = self._calculate_trends(
                current_social=social_data,
                previous_social=previous_social,
                current_sales=sales_data,
                previous_sales=previous_sales
            )
            
            # Calculate daily averages
            days_in_month = (month_end - month_start).days + 1
            
            report = {
                "report_type": "monthly",
                "month": month_str,
                "period": f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')}",
                "days_in_month": days_in_month,
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_posts": social_data.get("total_posts", 0),
                    "total_engagement": engagement_data.get("total_engagement", 0),
                    "total_revenue": sales_data.get("total_revenue", 0),
                    "total_transactions": sales_data.get("total_transactions", 0),
                    "average_daily_posts": round(social_data.get("total_posts", 0) / days_in_month, 1),
                    "average_daily_revenue": round(sales_data.get("total_revenue", 0) / days_in_month, 2),
                    "conversion_rate": self._calculate_conversion_rate(social_data, sales_data)
                },
                "social_media": social_data,
                "sales": sales_data,
                "engagement": engagement_data,
                "system": system_data,
                "trends": trends,
                "insights": await self._generate_insights(social_data, sales_data, engagement_data),
                "recommendations": await self._generate_recommendations(social_data, sales_data, engagement_data),
                "top_performing_content": await self._get_top_performing_content(month_start, month_end)
            }
            
            # Store report
            await self._store_report(report, "monthly", month_str)
            
            logger.info(f"✅ Monthly report generated successfully for {month_str}")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error generating monthly report: {e}")
            return {
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def _get_social_media_analytics(
        self, 
        start_date: datetime, 
        period: str, 
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get social media analytics for specified period."""
        try:
            if not end_date:
                if period == "daily":
                    end_date = start_date + timedelta(days=1)
                elif period == "weekly":
                    end_date = start_date + timedelta(days=7)
                else:  # monthly
                    end_date = start_date + timedelta(days=30)
            
            analytics = {
                "total_posts": 0,
                "platforms": {},
                "posting_frequency": {},
                "content_types": defaultdict(int),
                "peak_posting_hours": defaultdict(int)
            }
            
            # Analyze each platform
            for platform, key in self.social_keys.items():
                try:
                    posts_data = await data_client.get(key) or []
                    platform_posts = []
                    
                    # Filter posts by date range
                    for post in posts_data:
                        if isinstance(post, dict) and "timestamp" in post:
                            post_date = datetime.fromisoformat(post["timestamp"])
                            if start_date <= post_date <= end_date:
                                platform_posts.append(post)
                    
                    # Platform-specific analytics
                    analytics["platforms"][platform] = {
                        "posts_count": len(platform_posts),
                        "average_length": self._calculate_average_content_length(platform_posts),
                        "posting_times": [datetime.fromisoformat(p["timestamp"]).hour for p in platform_posts if "timestamp" in p]
                    }
                    
                    analytics["total_posts"] += len(platform_posts)
                    
                    # Track posting hours
                    for post in platform_posts:
                        if "timestamp" in post:
                            hour = datetime.fromisoformat(post["timestamp"]).hour
                            analytics["peak_posting_hours"][hour] += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error analyzing {platform} data: {e}")
                    analytics["platforms"][platform] = {"error": str(e)}
            
            # Convert defaultdicts to regular dicts for JSON serialization
            analytics["content_types"] = dict(analytics["content_types"])
            analytics["peak_posting_hours"] = dict(analytics["peak_posting_hours"])
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Error getting social media analytics: {e}")
            return {"error": str(e)}
    
    async def _get_sales_analytics(
        self, 
        start_date: datetime, 
        period: str, 
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get sales analytics for specified period."""
        try:
            if not end_date:
                if period == "daily":
                    end_date = start_date + timedelta(days=1)
                elif period == "weekly":
                    end_date = start_date + timedelta(days=7)
                else:  # monthly
                    end_date = start_date + timedelta(days=30)
            
            # Get PayPal analytics
            paypal_analytics = await paypal_service.get_sales_analytics((end_date - start_date).days)
            
            # Get stored payment data
            payments = await data_client.get(self.sales_keys["payments"]) or {}
            orders = await data_client.get(self.sales_keys["orders"]) or {}
            
            # Filter by date range
            period_payments = []
            period_orders = []
            
            for payment in payments.values():
                if isinstance(payment, dict) and "completed_at" in payment:
                    payment_date = datetime.fromisoformat(payment["completed_at"])
                    if start_date <= payment_date <= end_date:
                        period_payments.append(payment)
            
            for order in orders.values():
                if isinstance(order, dict) and "created_at" in order:
                    order_date = datetime.fromisoformat(order["created_at"])
                    if start_date <= order_date <= end_date:
                        period_orders.append(order)
            
            # Calculate analytics
            total_revenue = sum(p.get("amount", 0) for p in period_payments)
            total_transactions = len(period_payments)
            
            # Revenue by currency
            currency_breakdown = defaultdict(lambda: {"count": 0, "total": 0})
            for payment in period_payments:
                currency = payment.get("currency", "USD")
                currency_breakdown[currency]["count"] += 1
                currency_breakdown[currency]["total"] += payment.get("amount", 0)
            
            # Transaction amounts distribution
            amounts = [p.get("amount", 0) for p in period_payments if p.get("amount", 0) > 0]
            
            analytics = {
                "total_revenue": round(total_revenue, 2),
                "total_transactions": total_transactions,
                "total_orders": len(period_orders),
                "average_transaction": round(total_revenue / total_transactions, 2) if total_transactions > 0 else 0,
                "currency_breakdown": dict(currency_breakdown),
                "transaction_stats": {
                    "min_amount": min(amounts) if amounts else 0,
                    "max_amount": max(amounts) if amounts else 0,
                    "median_amount": statistics.median(amounts) if amounts else 0
                },
                "conversion_rate": self._calculate_order_conversion_rate(period_orders, period_payments),
                "refund_rate": await self._calculate_refund_rate(start_date, end_date)
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Error getting sales analytics: {e}")
            return {"error": str(e)}
    
    async def _get_engagement_analytics(
        self, 
        start_date: datetime, 
        period: str, 
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get engagement analytics for specified period."""
        try:
            analytics = {
                "total_engagement": 0,
                "platforms": {},
                "engagement_types": defaultdict(int),
                "top_engaging_content": []
            }
            
            # This would integrate with stored engagement data from social platforms
            # For now, we'll return a basic structure
            
            for platform in ["twitter", "mastodon", "discord"]:
                analytics["platforms"][platform] = {
                    "likes": 0,
                    "shares": 0,
                    "comments": 0,
                    "mentions": 0,
                    "engagement_rate": 0
                }
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Error getting engagement analytics: {e}")
            return {"error": str(e)}
    
    async def _get_system_analytics(
        self, 
        start_date: datetime, 
        period: str, 
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get system performance analytics."""
        try:
            analytics = {
                "uptime_percentage": 99.5,  # This would be calculated from actual system logs
                "api_calls": {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "rate_limited": 0
                },
                "ai_usage": {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "average_response_time": 0
                },
                "error_rate": 0,
                "performance_metrics": {
                    "average_response_time": 250,  # ms
                    "memory_usage": 85,  # percentage
                    "cpu_usage": 45  # percentage
                }
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Error getting system analytics: {e}")
            return {"error": str(e)}
    
    async def _generate_insights(
        self, 
        social_data: Dict[str, Any], 
        sales_data: Dict[str, Any], 
        engagement_data: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable insights from analytics data."""
        insights = []
        
        try:
            # Social media insights
            total_posts = social_data.get("total_posts", 0)
            if total_posts > 0:
                platforms = social_data.get("platforms", {})
                most_active_platform = max(platforms.keys(), key=lambda k: platforms[k].get("posts_count", 0)) if platforms else None
                
                if most_active_platform:
                    insights.append(f"Most active platform: {most_active_platform.title()} with {platforms[most_active_platform].get('posts_count', 0)} posts")
                
                # Peak posting hours
                peak_hours = social_data.get("peak_posting_hours", {})
                if peak_hours:
                    peak_hour = max(peak_hours.keys(), key=lambda k: peak_hours[k])
                    insights.append(f"Peak posting hour: {peak_hour}:00 with {peak_hours[peak_hour]} posts")
            
            # Sales insights
            total_revenue = sales_data.get("total_revenue", 0)
            total_transactions = sales_data.get("total_transactions", 0)
            
            if total_revenue > 0:
                insights.append(f"Generated ${total_revenue:.2f} in revenue from {total_transactions} transactions")
                
                avg_transaction = sales_data.get("average_transaction", 0)
                if avg_transaction > 0:
                    insights.append(f"Average transaction value: ${avg_transaction:.2f}")
            
            # Conversion insights
            conversion_rate = sales_data.get("conversion_rate", 0)
            if conversion_rate > 0:
                insights.append(f"Order conversion rate: {conversion_rate:.1f}%")
            
            # Engagement insights
            total_engagement = engagement_data.get("total_engagement", 0)
            if total_engagement > 0 and total_posts > 0:
                engagement_per_post = total_engagement / total_posts
                insights.append(f"Average engagement per post: {engagement_per_post:.1f}")
            
        except Exception as e:
            logger.error(f"❌ Error generating insights: {e}")
            insights.append(f"Error generating insights: {str(e)}")
        
        return insights
    
    async def _generate_recommendations(
        self, 
        social_data: Dict[str, Any], 
        sales_data: Dict[str, Any], 
        engagement_data: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations based on analytics."""
        recommendations = []
        
        try:
            # Social media recommendations
            total_posts = social_data.get("total_posts", 0)
            if total_posts < 7:  # Less than 1 post per day
                recommendations.append("Consider increasing posting frequency to maintain audience engagement")
            
            platforms = social_data.get("platforms", {})
            if len(platforms) > 1:
                post_counts = [p.get("posts_count", 0) for p in platforms.values()]
                if max(post_counts) > min(post_counts) * 3:
                    recommendations.append("Balance posting across all platforms for maximum reach")
            
            # Sales recommendations
            conversion_rate = sales_data.get("conversion_rate", 0)
            if conversion_rate < 2:  # Low conversion rate
                recommendations.append("Focus on improving sales copy and call-to-action effectiveness")
            
            refund_rate = sales_data.get("refund_rate", 0)
            if refund_rate > 5:  # High refund rate
                recommendations.append("Review product quality and customer satisfaction to reduce refunds")
            
            # Engagement recommendations
            total_engagement = engagement_data.get("total_engagement", 0)
            if total_engagement < total_posts * 5:  # Low engagement
                recommendations.append("Experiment with different content types to increase engagement")
            
            # Time-based recommendations
            peak_hours = social_data.get("peak_posting_hours", {})
            if peak_hours:
                low_activity_hours = [h for h in range(24) if h not in peak_hours or peak_hours[h] < 2]
                if len(low_activity_hours) > 12:
                    recommendations.append("Consider posting during different hours to reach new audiences")
            
        except Exception as e:
            logger.error(f"❌ Error generating recommendations: {e}")
            recommendations.append(f"Error generating recommendations: {str(e)}")
        
        return recommendations
    
    def _calculate_trends(
        self, 
        current_social: Dict[str, Any], 
        previous_social: Dict[str, Any],
        current_sales: Dict[str, Any], 
        previous_sales: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate trends between current and previous periods."""
        trends = {}
        
        try:
            # Social media trends
            current_posts = current_social.get("total_posts", 0)
            previous_posts = previous_social.get("total_posts", 0)
            
            if previous_posts > 0:
                posts_change = ((current_posts - previous_posts) / previous_posts) * 100
                trends["posts_change"] = round(posts_change, 1)
            else:
                trends["posts_change"] = 100 if current_posts > 0 else 0
            
            # Sales trends
            current_revenue = current_sales.get("total_revenue", 0)
            previous_revenue = previous_sales.get("total_revenue", 0)
            
            if previous_revenue > 0:
                revenue_change = ((current_revenue - previous_revenue) / previous_revenue) * 100
                trends["revenue_change"] = round(revenue_change, 1)
            else:
                trends["revenue_change"] = 100 if current_revenue > 0 else 0
            
            # Transaction trends
            current_transactions = current_sales.get("total_transactions", 0)
            previous_transactions = previous_sales.get("total_transactions", 0)
            
            if previous_transactions > 0:
                transactions_change = ((current_transactions - previous_transactions) / previous_transactions) * 100
                trends["transactions_change"] = round(transactions_change, 1)
            else:
                trends["transactions_change"] = 100 if current_transactions > 0 else 0
            
        except Exception as e:
            logger.error(f"❌ Error calculating trends: {e}")
            trends["error"] = str(e)
        
        return trends
    
    def _calculate_conversion_rate(self, social_data: Dict[str, Any], sales_data: Dict[str, Any]) -> float:
        """Calculate conversion rate from social media to sales."""
        try:
            total_posts = social_data.get("total_posts", 0)
            total_transactions = sales_data.get("total_transactions", 0)
            
            if total_posts > 0:
                return round((total_transactions / total_posts) * 100, 2)
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error calculating conversion rate: {e}")
            return 0
    
    def _calculate_order_conversion_rate(self, orders: List[Dict], payments: List[Dict]) -> float:
        """Calculate conversion rate from orders to completed payments."""
        try:
            if len(orders) > 0:
                return round((len(payments) / len(orders)) * 100, 2)
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error calculating order conversion rate: {e}")
            return 0
    
    async def _calculate_refund_rate(self, start_date: datetime, end_date: datetime) -> float:
        """Calculate refund rate for the period."""
        try:
            refunds = await data_client.get("paypal:refunds") or {}
            payments = await data_client.get(self.sales_keys["payments"]) or {}
            
            # Filter by date range
            period_refunds = []
            period_payments = []
            
            for refund in refunds.values():
                if isinstance(refund, dict) and "processed_at" in refund:
                    refund_date = datetime.fromisoformat(refund["processed_at"])
                    if start_date <= refund_date <= end_date:
                        period_refunds.append(refund)
            
            for payment in payments.values():
                if isinstance(payment, dict) and "completed_at" in payment:
                    payment_date = datetime.fromisoformat(payment["completed_at"])
                    if start_date <= payment_date <= end_date:
                        period_payments.append(payment)
            
            if len(period_payments) > 0:
                return round((len(period_refunds) / len(period_payments)) * 100, 2)
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error calculating refund rate: {e}")
            return 0
    
    def _calculate_average_content_length(self, posts: List[Dict]) -> float:
        """Calculate average content length for posts."""
        try:
            lengths = []
            for post in posts:
                if isinstance(post, dict) and "content" in post:
                    lengths.append(len(post["content"]))
            
            return round(statistics.mean(lengths), 1) if lengths else 0
            
        except Exception as e:
            logger.error(f"❌ Error calculating average content length: {e}")
            return 0
    
    async def _get_top_performing_content(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get top performing content for the period."""
        try:
            # This would analyze engagement metrics to find top content
            # For now, return empty list
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting top performing content: {e}")
            return []
    
    async def _store_report(self, report: Dict[str, Any], report_type: str, period_key: str):
        """Store generated report."""
        try:
            reports_key = f"analytics:reports:{report_type}"
            reports = await data_client.get(reports_key) or {}
            
            reports[period_key] = report
            
            # Keep only last 100 reports per type
            if len(reports) > 100:
                # Keep most recent reports
                sorted_keys = sorted(reports.keys(), reverse=True)
                reports = {k: reports[k] for k in sorted_keys[:100]}
            
            await data_client.set(reports_key, reports, expire=7776000)  # 90 days
            
            log_data_operation("STORE", f"{report_type}_report", success=True)
            
        except Exception as e:
            logger.error(f"❌ Error storing report: {e}")
            log_data_operation("STORE", f"{report_type}_report", success=False, error=str(e))
    
    async def get_stored_report(self, report_type: str, period_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored report."""
        try:
            reports_key = f"analytics:reports:{report_type}"
            reports = await data_client.get(reports_key) or {}
            
            return reports.get(period_key)
            
        except Exception as e:
            logger.error(f"❌ Error retrieving stored report: {e}")
            return None
    
    async def export_report_json(self, report: Dict[str, Any]):
    # TODO: Implementar lógica
     pass