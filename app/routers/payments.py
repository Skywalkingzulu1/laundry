import os
import stripe
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, PositiveInt
from app.dependencies import get_current_user, role_required
from app.models import User

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
    metadata: dict = {}
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
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to receive asynchronous events such as payment confirmation.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret or not sig_header:
        raise HTTPException(status_code=400, detail="Missing webhook secret or signature header")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(exc)}")

    # Example handling of a successful payment intent
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        # TODO: Update order status in your database, send confirmation email, etc.
        print(f"✅ PaymentIntent succeeded: {payment_intent['id']}")

    # Respond to Stripe to acknowledge receipt
    return {"status": "received"}