import os
import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, PositiveInt

from app.dependencies import role_required
from app.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Stripe configuration
# ---------------------------------------------------------------------------
stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_api_key:
    # Development fallback – replace with real key in production
    stripe_api_key = "sk_test_123"
stripe.api_key = stripe_api_key

# Webhook secret for signature verification
stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# ---------------------------------------------------------------------------
# In‑memory stores (replace with persistent DB in production)
# ---------------------------------------------------------------------------
_payment_intent_store: Dict[str, Dict[str, Any]] = {}
_checkout_session_store: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class PaymentIntentResponse(BaseModel):
    client_secret: str


class CreateCheckoutSessionRequest(BaseModel):
    amount: PositiveInt
    currency: str = "usd"
    success_url: str
    cancel_url: str
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    url: str


class RefundRequest(BaseModel):
    payment_intent_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    amount: Optional[PositiveInt] = None  # amount to refund (in smallest currency unit)


class RefundResponse(BaseModel):
    id: str
    status: str
    amount: int
    currency: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe PaymentIntent and return its client_secret.

    The optional ``booking_id`` is stored alongside the intent ID so the webhook can
    later associate the successful payment with the correct booking.
    """
    try:
        # Merge any provided metadata with booking reference
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        metadata["customer_email"] = current_user.email

        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=metadata,
        )
        # Store for quick lookup (in real app persist to DB)
        _payment_intent_store[intent.id] = {
            "user_id": current_user.id,
            "booking_id": payload.booking_id,
            "metadata": metadata,
        }
        logger.info(f"Created PaymentIntent {intent.id} for user {current_user.email}")
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        logger.exception("Failed to create payment intent")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe Checkout Session for one‑off payments.
    """
    try:
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        metadata["customer_email"] = current_user.email

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": payload.currency,
                        "product_data": {"name": "Laundry Service"},
                        "unit_amount": payload.amount,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            metadata=metadata,
        )
        _checkout_session_store[session.id] = {
            "user_id": current_user.id,
            "booking_id": payload.booking_id,
            "metadata": metadata,
        }
        logger.info(f"Created Checkout Session {session.id} for user {current_user.email}")
        return CheckoutSessionResponse(url=session.url)
    except Exception as exc:
        logger.exception("Failed to create checkout session")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/refund", response_model=RefundResponse)
async def refund_payment(
    payload: RefundRequest,
    current_user: User = Depends(role_required("admin")),
):
    """
    Issue a refund for a PaymentIntent or a Checkout Session.
    """
    try:
        if payload.payment_intent_id:
            refund = stripe.Refund.create(
                payment_intent=payload.payment_intent_id,
                amount=payload.amount,
            )
        elif payload.checkout_session_id:
            # Retrieve the session to get its payment_intent
            session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
            if not getattr(session, "payment_intent", None):
                raise HTTPException(
                    status_code=400,
                    detail="Checkout session has no associated payment intent",
                )
            refund = stripe.Refund.create(
                payment_intent=session.payment_intent,
                amount=payload.amount,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Either payment_intent_id or checkout_session_id must be provided",
            )
        logger.info(
            f"Refund created: {refund.id} for user {current_user.email} (amount={refund.amount})"
        )
        return RefundResponse(
            id=refund.id,
            status=refund.status,
            amount=refund.amount,
            currency=refund.currency,
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error during refund")
        raise HTTPException(status_code=400, detail=exc.user_message)
    except Exception as exc:
        logger.exception("Unexpected error during refund")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to handle asynchronous events such as successful payments.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, stripe_webhook_secret
            )
        except ValueError as e:
            # Invalid payload
            logger.error(f"Invalid webhook payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f"Invalid webhook signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # If no secret is set, trust the payload (development only)
        event = stripe.Event.construct_from(
            stripe.util.json.loads(payload), stripe.api_key
        )

    # Handle the event
    event_type = event["type"]
    logger.info(f"Received Stripe event: {event_type}")

    if event_type == "payment_intent.succeeded":
        intent = event["data"]["object"]
        intent_id = intent["id"]
        logger.info(f"PaymentIntent succeeded: {intent_id}")
        # Here you would update your order/booking status in DB
        # Example: mark_booking_as_paid(_payment_intent_store[intent_id]["booking_id"])
    elif event_type == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        logger.info(f"Checkout Session completed: {session_id}")
        # Example: mark_booking_as_paid(_checkout_session_store[session_id]["booking_id"])
    else:
        logger.info(f"Unhandled event type: {event_type}")

    return JSONResponse(content={"status": "success"})