# Unauthenticated Reservation Lookup and Reservation Metadata Disclosure

## Summary

I identified reservation-related API endpoints that can be accessed without authentication.

The following endpoints were accessible without an authenticated session:

* `/v2/reservation/{id}`
* `/v2/reservations?confirmationCode={confirmationCode}&email={email}`

The second endpoint accepts a confirmation code and email address directly and returns distinguishable responses for different input conditions. The reservation-related API also exposes additional reservation metadata in its responses.

During testing, I was **not able to obtain a valid third-party reservation record**, so I am not claiming confirmed disclosure of another customer's PII, payment information, or travel details.

The security concern is that reservation lookup functionality is available without an authenticated session, potentially allowing reservation existence probing or unauthorized reservation access if valid identifiers/credentials can be obtained or guessed.

## Affected Endpoints

### Endpoint 1

`GET /v2/reservation/{id}`

No authentication was required to reach the endpoint.

I tested reservation identifiers and received responses indicating that the supplied reservations were invalid.

I was unable to identify a valid reservation ID during testing.

### Endpoint 2

`GET /v2/reservations?confirmationCode={confirmationCode}&email={email}`

This endpoint also did not require authentication.

The server response differs depending on the supplied parameters.

Examples observed:

**Missing parameters:**

`Invalid confirmation code or email`

**Invalid combination:**

`Invalid reservation for confirmation code X and email Y`

This behavior demonstrates that the endpoint processes reservation lookup requests without requiring an authenticated user session.

## Steps to Reproduce

### Test 1 — Direct reservation endpoint

1. Ensure that there is no authenticated application session.
2. Send the following request:

```bash
curl -sS "https://api.cruises.kayak.com/v2/reservation/1" | python3 -m json.tool
```

3. The server returned **HTTP 200 OK** (not 401 or 403).
4. Response:

```json
{
    "reservation": null,
    "enabledAutoCharge": true,
    "errors": [
        "Invalid reservation #1."
    ],
    "shoreExcursionsLink": null,
    "bookingDotComLink": null,
    "gratuityEstimation": {
        "gratuityPerPersonPerNight": 0.0,
        "totalGratuity": 0.0
    }
}
```

5. Replace `{id}` with other candidate identifiers (e.g., `2`, `100`, `500000`) — the same pattern repeats: HTTP 200 with `Invalid reservation #<id>`.

### Test 2 — Confirmation code + email lookup

1. Ensure that there is no authenticated application session.
2. Send the following request with missing parameters:

```bash
curl -sS "https://api.cruises.kayak.com/v2/reservations" | python3 -m json.tool
```

3. Response (HTTP 200 OK):

```json
{
    "reservation": null,
    "enabledAutoCharge": true,
    "errors": [
        "Invalid confirmation code or email."
    ],
    "shoreExcursionsLink": null,
    "bookingDotComLink": null,
    "gratuityEstimation": {
        "gratuityPerPersonPerNight": 0.0,
        "totalGratuity": 0.0
    }
}
```

4. Now send with an invalid confirmation code and email:

```bash
curl -sS "https://api.cruises.kayak.com/v2/reservations?confirmationCode=TEST&email=test@example.com" | python3 -m json.tool
```

5. Response (HTTP 200 OK — different error message):

```json
{
    "reservation": null,
    "enabledAutoCharge": true,
    "errors": [
        "Invalid reservation for confirmation code TEST and email test@example.com."
    ],
    "shoreExcursionsLink": null,
    "bookingDotComLink": null,
    "gratuityEstimation": {
        "gratuityPerPersonPerNight": 0.0,
        "totalGratuity": 0.0
    }
}
```

6. Both responses returned HTTP 200 without authentication. The server distinguishes between missing parameters and invalid combinations, confirming that the endpoint processes the lookup request.

## Observed Behavior

The reservation lookup functionality is reachable without authentication.

In particular, the confirmation-code/email endpoint distinguishes between different input states, including:

* missing/invalid parameters
* invalid reservation combinations

Additionally, reservation-related responses were observed to contain fields such as:

* `enabledAutoCharge`
* `gratuityEstimation`
* `shoreExcursionsLink`
* `bookingDotComLink`

These fields appear even when the reservation lookup does not result in a valid reservation record.

## Security Impact

The primary concern is the absence of an authentication requirement around reservation lookup functionality.

If an attacker can obtain, infer, or successfully guess valid reservation identifiers or confirmation-code/email combinations, the endpoint may potentially allow access to reservation information without an authenticated session.

The distinguishable responses may also assist an attacker in determining whether supplied reservation information corresponds to an existing reservation.

The potential for unauthorized reservation access could not be confirmed because I did not obtain a valid third-party reservation during testing.

## ID / Confirmation Code Analysis

### Observed Confirmation Code Format

The confirmation code observed during testing followed this format:

`KYK28DN4` — 7-character alphanumeric string (uppercase letters and digits).

This code was generated during a cabin hold operation on the booking platform. The code structure suggests:

* **Character set:** A-Z, 0-9 (36 possible characters per position)
* **Length:** 7 characters
* **Total keyspace:** 36^7 ≈ 78 billion combinations (if fully random)

However, I was unable to determine:

* Whether confirmation codes are truly random or follow an internal pattern/prefix
* Whether codes are sequential or predictable across reservations
* Whether the same confirmation code can be reused across different email addresses

If confirmation codes follow a predictable pattern (e.g., sequential assignment, internal prefixes, or time-based generation), the effective keyspace could be significantly smaller, making brute-force or targeted guessing more feasible.

### Rate Limiting Observation

During testing, I did not encounter rate limiting, account lockout, or IP-based blocking when sending multiple unauthenticated lookup requests to the affected endpoints.

This observation is based on limited manual testing. I did not perform systematic brute-force testing to confirm the absence of rate limiting at scale.

## CVSS Considerations

Per HackerOne's platform standards for IDOR with unpredictable IDs:

* **Attack Complexity:** The default assumption should be **AC:H** (High) since confirmation codes may be unpredictable.
* **Condition for AC:L:** If confirmation codes can be obtained through other application features, follow predictable patterns, or are leaked in other responses, the complexity may be lowered to **AC:L** (Low).

The severity should be determined based on:

1. Confirmation code entropy and predictability
2. Rate limiting effectiveness
3. Whether codes can be obtained through other application functions
4. Impact of data disclosure if a valid code is found

## Security Context

The application already protects other reservation-related functionality with authentication.

For example, the following authenticated endpoints returned HTTP 401 when accessed without authentication:

* `/v2/reservations/upcoming`
* `/api/auth/*`

This suggests that authentication controls exist elsewhere in the application, making the lack of authentication on the affected reservation lookup functionality potentially inconsistent with the intended access-control model.

## Expected Behavior

Reservation-specific information should only be returned after the server has verified that the requester is authorized to access the reservation.

If confirmation code + email is intentionally designed to act as a standalone reservation credential, the server should ensure that:

1. The credential combination is sufficiently unguessable.
2. Sensitive reservation information is not unnecessarily exposed.
3. Responses do not provide excessive information that facilitates enumeration.
4. Appropriate rate limiting and abuse detection are applied.
5. Error responses do not disclose unnecessary reservation metadata.

## Recommended Remediation

Review the authorization model for both affected endpoints.

For `/v2/reservation/{id}`:

* Require an authenticated and authorized session where appropriate.
* Verify that the authenticated user is authorized to access the requested reservation.
* Avoid relying solely on reservation identifiers for authorization.

For `/v2/reservations`:

* Review whether unauthenticated confirmation-code/email lookup is intended.
* If it is intended, treat the confirmation code as a security-sensitive credential.
* Apply strong rate limiting and anti-enumeration controls.
* Return generic responses where practical.
* Avoid exposing unnecessary reservation metadata in invalid/error responses.

## Evidence / Limitations

I intentionally did not perform large-scale enumeration or attempt to access other customers' reservations.

The testing therefore establishes the unauthenticated reservation lookup behavior but does **not** establish confirmed third-party reservation data disclosure.

I am providing this limitation explicitly so the report does not overstate the demonstrated impact.
