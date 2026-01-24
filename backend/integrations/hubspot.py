# hubspot.py

import json
import secrets
import base64
import asyncio
import requests
import httpx

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis
from integrations.integration_item import IntegrationItem


# =====================================================
# HubSpot App Credentials (PUT REAL VALUES HERE)
# =====================================================
CLIENT_ID = "3d66c469-f802-4187-bcf7-c838a2f2ea3e"
CLIENT_SECRET = "c365bd4b-dbc8-4d8f-8b2c-4d8394dbe23c"

REDIRECT_URI = "http://localhost:8000/integrations/hubspot/oauth2callback"

AUTHORIZATION_URL = (
    "https://app.hubspot.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    "&scope=crm.objects.contacts.read"
)

TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"


# =====================================================
# STEP 1: AUTHORIZE HUBSPOT
# =====================================================
async def authorize_hubspot(user_id: str, org_id: str):
    """
    Generates HubSpot OAuth URL and saves state in Redis
    """
    print("authorize_hubspot called", user_id, org_id)

    state_data = {
        "state": secrets.token_urlsafe(32),
        "user_id": user_id,
        "org_id": org_id,
    }

    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()

    await add_key_value_redis(
        f"hubspot_state:{org_id}:{user_id}",
        json.dumps(state_data),
        expire=600,
    )

    return f"{AUTHORIZATION_URL}&state={encoded_state}"


# =====================================================
# STEP 2: OAUTH CALLBACK
# =====================================================
async def oauth2callback_hubspot(request: Request):
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=error)

    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")

    state_data = json.loads(
        base64.urlsafe_b64decode(encoded_state).decode()
    )

    user_id = state_data["user_id"]
    org_id = state_data["org_id"]

    saved_state = await get_value_redis(
        f"hubspot_state:{org_id}:{user_id}"
    )

    if not saved_state:
        raise HTTPException(status_code=400, detail="State not found")

    # Exchange authorization code for access token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=response.text)

    await asyncio.gather(
        add_key_value_redis(
            f"hubspot_credentials:{org_id}:{user_id}",
            json.dumps(response.json()),
            expire=600,
        ),
        delete_key_redis(f"hubspot_state:{org_id}:{user_id}"),
    )

    # Close OAuth popup window
    return HTMLResponse(
        """
        <html>
          <script>
            window.close();
          </script>
        </html>
        """
    )


# =====================================================
# STEP 3: GET HUBSPOT CREDENTIALS
# =====================================================
async def get_hubspot_credentials(user_id: str, org_id: str):
    credentials = await get_value_redis(
        f"hubspot_credentials:{org_id}:{user_id}"
    )

    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found")

    await delete_key_redis(f"hubspot_credentials:{org_id}:{user_id}")

    return json.loads(credentials)


# =====================================================
# HELPER: CREATE INTEGRATION ITEM
# =====================================================
def create_integration_item_metadata_object(contact: dict) -> IntegrationItem:
    """
    Converts a HubSpot contact object into IntegrationItem
    """

    contact_id = contact.get("id")
    properties = contact.get("properties", {})

    email = properties.get("email", "No Email")
    firstname = properties.get("firstname", "")
    lastname = properties.get("lastname", "")

    name = f"{firstname} {lastname}".strip() or email

    return IntegrationItem(
        id=contact_id,
        type="hubspot_contact",
        name=name,
        directory=False,
        parent_id=None,
        parent_path_or_name="HubSpot",
        url="https://app.hubspot.com/contacts",
        visibility=True,
    )


# =====================================================
# STEP 4: LOAD HUBSPOT ITEMS (PART 2)
# =====================================================
async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    """
    Fetch HubSpot contacts and return them as IntegrationItem list
    """

    credentials = json.loads(credentials)

    access_token = credentials.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token missing")

    response = requests.get(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params={"limit": 10},
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"HubSpot API error: {response.text}",
        )

    data = response.json()
    results = data.get("results", [])

    integration_items = []

    for contact in results:
        item = create_integration_item_metadata_object(contact)
        integration_items.append(item)

    print("HubSpot Integration Items:")
    for item in integration_items:
        print(vars(item))

    return integration_items
