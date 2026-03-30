import os
import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, PositiveInt

from app.dependencies import role_required
from app.models import User

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
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
@router.post(
    "/create-payment-intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
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
        metadata["user_id"] = str(current_user.id)

        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=metadata,
        )
        # Store for quick lookup (demo purposes)
        _payment_intent_store[intent.id] = {
            "user_id": current_user.id,
            "booking_id": payload.booking_id,
            "amount": payload.amount,
            "currency": payload.currency,
            "metadata": metadata,
        }
        logger.info(f"Created PaymentIntent {intent.id} for user {current_user.email}")
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error while creating PaymentIntent")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe Checkout Session and return the redirect URL.

    ``booking_id`` is stored in the session metadata for later correlation.
    """
    try:
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        metadata["user_id"] = str(current_user.id)

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
            "amount": payload.amount,
            "currency": payload.currency,
            "metadata": metadata,
        }
        logger.info(f"Created Checkout Session {session.id} for user {current_user.email}")
        return CheckoutSessionResponse(url=session.url)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error while creating Checkout Session")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to receive asynchronous events such as payment success.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify signature if secret is configured
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
        # No secret configured – trust the payload (not recommended for prod)
        logger.warning("STRIPE_WEBHOOK_SECRET not set – skipping signature verification")
        event = stripe.Event.construct_from(
            stripe.util.convert_to_dict(payload), stripe.api_key
        )

    # Handle the event
    logger.info(f"Received Stripe event: {event.type}")

    if event.type == "payment_intent.succeeded":
        intent = event.data.object  # type: ignore
        logger.info(
            f"PaymentIntent succeeded: {intent.id}, amount: {intent.amount}, metadata: {intent.metadata}"
        )
        # Here you would update your booking/order status using intent.metadata["booking_id"]
    elif event.type == "checkout.session.completed":
        session = event.data.object  # type: ignore
        logger.info(
            f"Checkout Session completed: {session.id}, payment_intent: {session.payment_intent}, metadata: {session.metadata}"
        )
        # Update booking/order status using session.metadata["booking_id"]
    else:
        logger.info(f"Unhandled event type: {event.type}")

    return JSONResponse(content={"status": "success"})


@router.post(
    "/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_200_OK,
)
async def refund_payment(
    payload: RefundRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Refund a payment either by PaymentIntent ID or Checkout Session ID.
    """
    if not payload.payment_intent_id and not payload.checkout_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either payment_intent_id or checkout_session_id must be provided",
        )

    try:
        # Resolve the PaymentIntent ID if a Checkout Session ID was supplied
        payment_intent_id = payload.payment_intent_id
        if payload.checkout_session_id:
            session = _checkout_session_store.get(payload.checkout_session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Checkout session not found",
                )
            # Retrieve the real Stripe session to get the linked PaymentIntent
            stripe_session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
            payment_intent_id = stripe_session.payment_intent

        if not payment_intent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to determine payment_intent_id for refund",
            )

        refund_params: Dict[str, Any] = {"payment_intent": payment_intent_id}
        if payload.amount:
            refund_params["amount"] = payload.amount

        refund = stripe.Refund.create(**refund_params)

        logger.info(
            f"Created refund {refund.id} for payment_intent {payment_intent_id} (user {current_user.email})"
        )
        return RefundResponse(
            id=refund.id,
            status=refund.status,
            amount=refund.amount,
            currency=refund.currency,
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error while creating refund")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )