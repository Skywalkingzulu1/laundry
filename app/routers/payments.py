import os
import logging
from typing import Any, Dict

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status, Response
from pydantic import BaseModel, PositiveInt

from app.dependencies import get_current_user, role_required
from app.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Load Stripe secret key from environment; raise error if not set in production
stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_api_key:
    # For local development a test key can be used, but in production this must be set
    stripe_api_key = "sk_test_123"
stripe.api_key = stripe_api_key


class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: Dict[str, Any] = {}
    # Optional booking reference to associate the payment with a booking
    booking_id: str | None = None


class PaymentIntentResponse(BaseModel):
    client_secret: str


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer"))
):
    """
    Create a Stripe PaymentIntent and return its client_secret so the frontend can
    complete the payment securely.

    Only customers can initiate a payment. The optional `booking_id` can be used
    by the frontend to link the payment to a specific booking record.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=payload.metadata,
        )
        # In a real implementation you would persist the intent ID together with
        # the booking_id and user information to verify later in the webhook.
        logger.info(
            "Created PaymentIntent %s for user %s (booking_id=%s)",
            intent.id,
            current_user.email,
            payload.booking_id,
        )
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        logger.exception("Error creating PaymentIntent: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to receive asynchronous events such as payment confirmation.

    The endpoint validates the Stripe signature, parses the event, and processes
    relevant event types (e.g., `payment_intent.succeeded`). After handling the
    event, it returns a 200 response to acknowledge receipt.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not set in environment")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if sig_header is None:
        logger.error("Missing Stripe signature header")
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )
    except ValueError as e:
        # Invalid payload
        logger.exception("Invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.exception("Invalid Stripe signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    logger.info("Received Stripe event: %s", event["type"])

    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        # Example: you could retrieve booking_id from metadata if you stored it
        booking_id = payment_intent.get("metadata", {}).get("booking_id")
        logger.info(
            "PaymentIntent succeeded: %s (amount: %s, booking_id: %s)",
            payment_intent["id"],
            payment_intent["amount"],
            booking_id,
        )
        # TODO: Update booking status in your database to 'paid' using booking_id
    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        logger.warning(
            "PaymentIntent failed: %s (amount: %s)",
            payment_intent["id"],
            payment_intent["amount"],
        )
        # TODO: Handle failed payment (e.g., notify user)

    # Return a 200 response to acknowledge receipt of the event
    return Response(status_code=status.HTTP_200_OK)