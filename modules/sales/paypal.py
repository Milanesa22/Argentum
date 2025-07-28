"""
AURELIUS PayPal Integration Module
Handles PayPal API integration for payment processing, sales tracking, and webhooks.
"""

import asyncio
import aiohttp
import json
import base64
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import hmac
import hashlib
import discord

from ...config import config
from ...logging_config import get_logger, log_payment_event, log_api_call
from ...utils.security import validate_and_sanitize_input, SecurityValidator
from ...db.redis_client import data_client

logger = get_logger("PAYPAL")

class AureliusPayPal:
    """
    PayPal API integration for payment processing, order management, and webhook handling.
    Supports both sandbox and live environments with comprehensive error handling.
    """
    
    async def generate_payment_link(
        self,
        user_id: str,
        amount: float,
        description: str = "AURELIUS Service"
    ) -> Union[str, None]:
        """
        Generate a PayPal payment link for a given user.
        """
        try:
            metadata = {"discord_user_id": user_id}  # ✅ clave para el webhook
            result = await self.create_order(
                amount=amount,
                description=description,
                metadata=metadata
            )
            if result["success"]:
                return result.get("approval_url")
            else:
                logger.warning(f"⚠️ Failed to generate payment link for {user_id}: {result.get('error')}")
                return None
        except Exception as e:
            logger.error(f"❌ Exception in generate_payment_link: {e}")
            return None

    
    async def check_if_user_paid(self, user_id: str, platform: str = "discord") -> bool:
        """
        Chequea si un usuario (por user_id) ya pagó (por ejemplo en Discord).
        Retorna True si ya pagó, False si no.
        """
        key = f"paypal_pago_{user_id}"
        pago = await data_client.get(key)
        return pago == "paid"

    def __init__(self):
        self.client_id = config.PAYPAL_CLIENT_ID
        self.client_secret = config.PAYPAL_CLIENT_SECRET
        self.mode = "live"
        self.webhook_id = config.PAYPAL_WEBHOOK_ID

        self.base_url = "https://api-m.paypal.com"
        self.http_client = None
        self.access_token = None
        self.token_expires_at = None

        self.orders_key = "paypal:orders"
        self.payments_key = "paypal:payments"
        self.webhooks_key = "paypal:webhooks"
        self.customers_key = "paypal:customers"

    async def async_initialize(self):
        """Async initialization for HTTP client."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "en_US"
            }
            self.http_client = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )
            logger.info(f"✅ PayPal client initialized | Mode: {self.mode}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize PayPal client: {e}")
            raise

    async def _get_access_token(self) -> str:
        """
        Get or refresh PayPal access token.
        Returns valid access token.
        """
        try:
            # Check if current token is still valid
            if (
                self.access_token
                and self.token_expires_at
                and datetime.now() < self.token_expires_at - timedelta(minutes=5)
            ):
                return self.access_token
            # Prepare authentication
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode("ascii")
            auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = "grant_type=client_credentials"
            log_api_call("PayPal", "POST /v1/oauth2/token", "POST")
            # Request access token **usando un contexto async**
            async with self.http_client.post(
                f"{self.base_url}/v1/oauth2/token", headers=headers, data=data
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    self.access_token = response_data.get("access_token")
                    expires_in = response_data.get("expires_in", 3000)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    logger.info("✅ PayPal access token obtained")
                    return self.access_token
                else:
                    error_text = await response.text()
                    error_msg = f"Failed to get PayPal access token: {response.status} - {error_text}"
                    logger.error(f"❌ {error_msg}")
                    log_api_call("PayPal", "POST /v1/oauth2/token", "POST", status=response.status)
                    raise Exception(error_msg)
        except Exception as e:
            logger.error(f"❌ Error getting PayPal access token: {e}")
            raise

    async def close(self):
        """Close HTTP client."""
        if self.http_client:
            await self.http_client.close()

    async def _make_api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated API request to PayPal.
        Returns response data or raises exception.
        """
        try:
            # Get valid access token
            token = await self._get_access_token()

            # Prepare headers
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": f"aurelius-{datetime.now().timestamp()}"
            }

            # Prepare URL
            url = f"{self.base_url}{endpoint}"

            log_api_call("PayPal", f"{method} {endpoint}", method)

            # Make request
            async with self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                json=data if data else None,
                params=params if params else None
            ) as response:

                response_text = await response.text()

                if response.status in [200, 201, 202, 204]:
                    log_api_call("PayPal", f"{method} {endpoint}", method, status=response.status)

                    if response_text:
                        try:
                            return json.loads(response_text)
                        except Exception:
                            return {"success": True, "raw_response": response_text}
                    else:
                        return {"success": True}
                else:
                    error_msg = f"PayPal API error: {response.status} - {response_text}"
                    logger.error(f"❌ {error_msg}")
                    log_api_call("PayPal", f"{method} {endpoint}", method, status=response.status)

                    # Try to parse error response
                    try:
                        error_data = json.loads(response_text)
                        return {
                            "error": True,
                            "status": response.status,
                            "details": error_data
                        }
                    except Exception:
                        return {
                            "error": True,
                            "status": response.status,
                            "message": response_text
                        }

        except Exception as e:
            logger.error(f"❌ PayPal API request failed: {e}")
            raise

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "AURELIUS Service",
        customer_email: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a PayPal order for payment.
        Returns order data with payment links.
        """
        try:
            if amount <= 0:
                return {
                    "success": False,
                    "error": "Amount must be greater than 0"
                }

            description = validate_and_sanitize_input(description, "description")

            # Prepare order data
            order_data = {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "amount": {
                            "currency_code": currency,
                            "value": f"{amount:.2f}"
                        },
                        "description": description
                    }
                ],
                "application_context": {
                    "brand_name": "AURELIUS",
                    "landing_page": "BILLING",
                    "user_action": "PAY_NOW"
                }
            }

            # Add return URLs if provided
            if return_url or cancel_url:
                order_data["application_context"]["return_url"] = return_url or "https://example.com/success"
                order_data["application_context"]["cancel_url"] = cancel_url or "https://example.com/cancel"

            # Create order
            response = await self._make_api_request("POST", "/v2/checkout/orders", order_data)

            if response.get("error"):
                log_payment_event("order_creation", amount, currency, error=str(response))
                return {
                    "success": False,
                    "error": response.get("message", "Failed to create PayPal order"),
                    "details": response.get("details")
                }

            order_id = response["id"]

            # Extract approval URL
            approval_url = None
            for link in response.get("links", []):
                if link["rel"] == "approve":
                    approval_url = link["href"]
                    break

            # Store order data
            order_record = {
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "description": description,
                "customer_email": customer_email,
                "status": response["status"],
                "created_at": datetime.now().isoformat(),
                "approval_url": approval_url,
                "metadata": metadata or {}
            }

            await self._store_order(order_record)

            log_payment_event("order_creation", amount, currency, order_id)
            logger.info(f"✅ PayPal order created | ID: {order_id} | Amount: {amount} {currency}")

            return {
                "success": True,
                "order_id": order_id,
                "status": response["status"],
                "approval_url": approval_url,
                "amount": amount,
                "currency": currency,
                "created_at": order_record["created_at"]
            }

        except Exception as e:
            error_msg = f"Failed to create PayPal order: {e}"
            logger.error(f"❌ {error_msg}")
            log_payment_event("order_creation", amount, currency, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    async def capture_order(self, order_id: str) -> Dict[str, Any]:
        """
        Capture payment for an approved order.
        Returns capture details.
        """
        try:
            # Capture the order
            response = await self._make_api_request("POST", f"/v2/checkout/orders/{order_id}/capture")

            if response.get("error"):
                log_payment_event("order_capture", transaction_id=order_id, error=str(response))
                return {
                    "success": False,
                    "error": response.get("message", "Failed to capture PayPal order"),
                    "details": response.get("details")
                }

            # Extract capture details
            capture_id = None
            amount = 0
            currency = "USD"

            for purchase_unit in response.get("purchase_units", []):
                for capture in purchase_unit.get("payments", {}).get("captures", []):
                    capture_id = capture["id"]
                    amount = float(capture["amount"]["value"])
                    currency = capture["amount"]["currency_code"]
                    break

            # Update order record
            await self._update_order_status(order_id, "COMPLETED", {
                "capture_id": capture_id,
                "captured_at": datetime.now().isoformat()
            })

            # Store payment record
            payment_record = {
                "payment_id": capture_id,
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "status": "COMPLETED",
                "captured_at": datetime.now().isoformat(),
                "payer_info": response.get("payer", {})
            }

            await self._store_payment(payment_record)

            log_payment_event("order_capture", amount, currency, capture_id)
            logger.info(f"✅ PayPal order captured | Order: {order_id} | Capture: {capture_id}")

            return {
                "success": True,
                "order_id": order_id,
                "capture_id": capture_id,
                "amount": amount,
                "currency": currency,
                "status": "COMPLETED",
                "captured_at": payment_record["captured_at"]
            }

        except Exception as e:
            error_msg = f"Failed to capture PayPal order {order_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_payment_event("order_capture", transaction_id=order_id, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """
        Get details of a PayPal order.
        Returns order information.
        """
        try:
            response = await self._make_api_request("GET", f"/v2/checkout/orders/{order_id}")

            if response.get("error"):
                return {
                    "success": False,
                    "error": response.get("message", "Failed to get order details")
                }

            # Extract order details
            order_details = {
                "success": True,
                "order_id": response["id"],
                "status": response["status"],
                "created_at": response.get("create_time"),
                "updated_at": response.get("update_time"),
                "purchase_units": []
            }

            for unit in response.get("purchase_units", []):
                unit_details = {
                    "amount": {
                        "value": unit["amount"]["value"],
                        "currency": unit["amount"]["currency_code"]
                    },
                    "description": unit.get("description", ""),
                    "payments": unit.get("payments", {})
                }
                order_details["purchase_units"].append(unit_details)

            # Add payer information if available
            if response.get("payer"):
                order_details["payer"] = response["payer"]

            logger.info(f"📊 Retrieved PayPal order details | ID: {order_id}")
            return order_details

        except Exception as e:
            error_msg = f"Failed to get PayPal order details {order_id}: {e}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    async def refund_payment(self, capture_id: str, amount: Optional[float] = None, reason: str = "Customer request") -> Dict[str, Any]:
        """
        Refund a captured payment.
        Returns refund details.
        """
        try:
            # Prepare refund data
            refund_data = {
                "note_to_payer": validate_and_sanitize_input(reason, "refund_reason")
            }

            if amount:
                # Partial refund
                refund_data["amount"] = {
                    "value": f"{amount:.2f}",
                    "currency_code": "USD"  # Should be dynamic based on original payment
                }

            # Process refund
            response = await self._make_api_request("POST", f"/v2/payments/captures/{capture_id}/refund", refund_data)

            if response.get("error"):
                log_payment_event("refund", amount, transaction_id=capture_id, error=str(response))
                return {
                    "success": False,
                    "error": response.get("message", "Failed to process refund"),
                    "details": response.get("details")
                }

            refund_id = response["id"]
            refund_amount = float(response["amount"]["value"])
            currency = response["amount"]["currency_code"]

            # Store refund record
            refund_record = {
                "refund_id": refund_id,
                "capture_id": capture_id,
                "amount": refund_amount,
                "currency": currency,
                "reason": reason,
                "status": response["status"],
                "created_at": datetime.now().isoformat()
            }

            await self._store_refund(refund_record)

            log_payment_event("refund", refund_amount, currency, refund_id)
            logger.info(f"✅ PayPal refund processed | Refund: {refund_id} | Amount: {refund_amount} {currency}")

            return {
                "success": True,
                "refund_id": refund_id,
                "capture_id": capture_id,
                "amount": refund_amount,
                "currency": currency,
                "status": response["status"],
                "created_at": refund_record["created_at"]
            }

        except Exception as e:
            error_msg = f"Failed to refund PayPal payment {capture_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_payment_event("refund", amount, transaction_id=capture_id, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    async def handle_webhook(self, webhook_data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Handle PayPal webhook notifications.
        Returns processing result.
        """
        try:
            # Sanitize webhook data
            webhook_data = SecurityValidator.sanitize_webhook_data(webhook_data)

            event_type = webhook_data.get("event_type")
            resource = webhook_data.get("resource", {})

            logger.info(f"🔔 Processing PayPal webhook | Type: {event_type}")

            # Store webhook for audit
            webhook_record = {
                "event_id": webhook_data.get("id"),
                "event_type": event_type,
                "resource_type": resource.get("resource_type"),
                "received_at": datetime.now().isoformat(),
                "data": webhook_data
            }

            await self._store_webhook(webhook_record)

            # Process different event types
            result = {"success": True, "processed": False}

            if event_type == "CHECKOUT.ORDER.APPROVED":
                result = await self._handle_order_approved(resource)
            elif event_type == "PAYMENT.CAPTURE.COMPLETED":
                result = await self._handle_payment_completed(resource)
            elif event_type == "PAYMENT.CAPTURE.DENIED":
                result = await self._handle_payment_denied(resource)
            elif event_type == "PAYMENT.CAPTURE.REFUNDED":
                result = await self._handle_payment_refunded(resource)
            else:
                logger.info(f"ℹ️  Unhandled webhook event type: {event_type}")
                result = {"success": True, "processed": False, "message": f"Event type {event_type} not handled"}

            return result

        except Exception as e:
            error_msg = f"Failed to handle PayPal webhook: {e}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    async def _handle_order_approved(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Handle order approved webhook."""
        try:
            order_id = resource.get("id")

            # Update order status
            await self._update_order_status(order_id, "APPROVED")

            logger.info(f"✅ Order approved webhook processed | Order: {order_id}")
            return {"success": True, "processed": True, "action": "order_approved"}

        except Exception as e:
            logger.error(f"❌ Error handling order approved webhook: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_payment_completed(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment completed webhook. ENVÍA el código completo por Discord."""
        try:
            capture_id = resource.get("id")
            amount = float(resource.get("amount", {}).get("value", 0))
            currency = resource.get("amount", {}).get("currency_code", "USD")

            # 1. Recuperar datos personalizados del pago (guardar el discord_user_id en 'custom_id' al crear la orden)
            custom_id = resource.get("custom_id") or resource.get("custom") or ""
            discord_user_id = custom_id.strip()  # Cambia esto según cómo guardes el ID en PayPal

            # Store/update payment record
            payment_record = {
                "payment_id": capture_id,
                "amount": amount,
                "currency": currency,
                "status": "COMPLETED",
                "completed_at": datetime.now().isoformat(),
                "webhook_data": resource
            }
            await self._store_payment(payment_record)

            log_payment_event("payment_completed", amount, currency, capture_id)
            logger.info(f"✅ Payment completed webhook processed | Capture: {capture_id}")

            # 2. ENVIAR ARCHIVO/CÓDIGO por Discord
            # Marca el pago como recibido para ese user_id
            if discord_user_id:
                await data_client.set(f"paypal_pago_{discord_user_id}", "paid", expire=7776000)
                from aurelius.social.discord import discord_service
                filename = "workflow_entregado.py"
                await discord_service.send_code_to_user(discord_user_id, filename)
                logger.info(f"✅ Código completo enviado a Discord user {discord_user_id} tras pago.")
            else:
                logger.warning("⚠️ No se encontró discord_user_id en el pago para envío de código.")


            return {"success": True, "processed": True, "action": "payment_completed"}

        except Exception as e:
            logger.error(f"❌ Error handling payment completed webhook: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_payment_denied(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment denied webhook."""
        try:
            capture_id = resource.get("id")

            # Update payment status
            await self._update_payment_status(capture_id, "DENIED")

            log_payment_event("payment_denied", transaction_id=capture_id)
            logger.warning(f"⚠️  Payment denied webhook processed | Capture: {capture_id}")

            return {"success": True, "processed": True, "action": "payment_denied"}

        except Exception as e:
            logger.error(f"❌ Error handling payment denied webhook: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_payment_refunded(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment refunded webhook."""
        try:
            refund_id = resource.get("id")
            amount = float(resource.get("amount", {}).get("value", 0))
            currency = resource.get("amount", {}).get("currency_code", "USD")

            # Store refund record
            refund_record = {
                "refund_id": refund_id,
                "amount": amount,
                "currency": currency,
                "status": "COMPLETED",
                "processed_at": datetime.now().isoformat(),
                "webhook_data": resource
            }

            await self._store_refund(refund_record)

            log_payment_event("refund_completed", amount, currency, refund_id)
            logger.info(f"✅ Refund completed webhook processed | Refund: {refund_id}")

            return {"success": True, "processed": True, "action": "refund_completed"}

        except Exception as e:
            logger.error(f"❌ Error handling refund webhook: {e}")
            return {"success": False, "error": str(e)}

    # Data storage methods
    async def _store_order(self, order_data: Dict[str, Any]):
        """Store order data."""
        try:
            orders = await data_client.get(self.orders_key) or {}
            orders[order_data["order_id"]] = order_data
            await data_client.set(self.orders_key, orders, expire=7776000)  # 90 days
        except Exception as e:
            logger.error(f"❌ Error storing order data: {e}")

    async def _store_payment(self, payment_data: Dict[str, Any]):
        """Store payment data."""
        try:
            payments = await data_client.get(self.payments_key) or {}
            payments[payment_data["payment_id"]] = payment_data
            await data_client.set(self.payments_key, payments, expire=7776000)  # 90 days
        except Exception as e:
            logger.error(f"❌ Error storing payment data: {e}")

    async def _store_refund(self, refund_data: Dict[str, Any]):
        """Store refund data."""
        try:
            refunds_key = "paypal:refunds"
            refunds = await data_client.get(refunds_key) or {}
            refunds[refund_data["refund_id"]] = refund_data
            await data_client.set(refunds_key, refunds, expire=7776000)  # 90 days
        except Exception as e:
            logger.error(f"❌ Error storing refund data: {e}")

    async def _store_webhook(self, webhook_data: Dict[str, Any]):
        """Store webhook data."""
        try:
            webhooks = await data_client.get(self.webhooks_key) or []
            webhooks.append(webhook_data)

            # Keep only last 1000 webhooks
            if len(webhooks) > 1000:
                webhooks = webhooks[-1000:]

            await data_client.set(self.webhooks_key, webhooks, expire=2592000)  # 30 days
        except Exception as e:
            logger.error(f"❌ Error storing webhook data: {e}")

    async def _update_order_status(self, order_id: str, status: str, additional_data: Optional[Dict[str, Any]] = None):
        """Update order status."""
        try:
            orders = await data_client.get(self.orders_key) or {}
            if order_id in orders:
                orders[order_id]["status"] = status
                orders[order_id]["updated_at"] = datetime.now().isoformat()
                if additional_data:
                    orders[order_id].update(additional_data)
                await data_client.set(self.orders_key, orders, expire=7776000)
        except Exception as e:
            logger.error(f"❌ Error updating order status: {e}")

    async def _update_payment_status(self, payment_id: str, status: str):
        """Update payment status."""
        try:
            payments = await data_client.get(self.payments_key) or {}
            if payment_id in payments:
                payments[payment_id]["status"] = status
                payments[payment_id]["updated_at"] = datetime.now().isoformat()
                await data_client.set(self.payments_key, payments, expire=7776000)
        except Exception as e:
            logger.error(f"❌ Error updating payment status: {e}")

    async def get_sales_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get sales analytics for specified period."""
        try:
            # Get all payments
            payments = await data_client.get(self.payments_key) or {}

            # Filter by date range
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_payments = []

            for payment in payments.values():
                payment_date = datetime.fromisoformat(payment.get("completed_at", payment.get("created_at", "1970-01-01")))
                if payment_date >= cutoff_date and payment.get("status") == "COMPLETED":
                    recent_payments.append(payment)

            # Calculate analytics
            total_revenue = sum(payment.get("amount", 0) for payment in recent_payments)
            total_transactions = len(recent_payments)

            # Group by currency
            currency_breakdown = {}
            for payment in recent_payments:
                currency = payment.get("currency", "USD")
                if currency not in currency_breakdown:
                    currency_breakdown[currency] = {"count": 0, "total": 0}
                currency_breakdown[currency]["count"] += 1
                currency_breakdown[currency]["total"] += payment.get("amount", 0)

            analytics = {
                "period_days": days,
                "total_revenue": round(total_revenue, 2),
                "total_transactions": total_transactions,
                "average_transaction": round(total_revenue / total_transactions, 2) if total_transactions > 0 else 0,
                "currency_breakdown": currency_breakdown,
                "generated_at": datetime.now().isoformat()
            }

            logger.info(f"📊 Generated PayPal sales analytics | Revenue: ${total_revenue:.2f} | Transactions: {total_transactions}")
            return analytics

        except Exception as e:
            logger.error(f"❌ Error generating sales analytics: {e}")
            return {
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }

# ------ QUICK ACCESS FUNCTIONS --------

paypal_service = AureliusPayPal()
# Recuerda inicializar tras instanciar:
# await paypal_service.async_initialize()

async def create_payment_order(amount: float, description: str, **kwargs) -> Dict[str, Any]:
    """Quick function to create a PayPal order."""
    return await paypal_service.create_order(amount, description=description, **kwargs)

async def capture_payment_order(order_id: str) -> Dict[str, Any]:
    """Quick function to capture a PayPal order."""
    return await paypal_service.capture_order(order_id)

async def process_payment_webhook(webhook_data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    """Quick function to process PayPal webhooks."""
    return await paypal_service.handle_webhook(webhook_data, headers)

async def get_payment_analytics(days: int = 30) -> Dict[str, Any]:
    """Quick function to get payment analytics."""
    return await paypal_service.get_sales_analytics(days)
