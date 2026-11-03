# Retained attempts

First attempt: `tests-20261103T010133.654997Z-ec59d627.json`.
30 Python tests ran: 28 passed, 2 failed; Pester 3.4.0: 2 passed, 0 failed.
Both failures shared a reference-adapter defect: it required the optional `tags`
display field from the template fixture. The reference design legitimately omits
tags. The promotion negative test consequently stopped before reaching its
intended source gate. No operation or contract bytes were changed.

Correction: exclude optional tags/subcategory from reference required fields.
The reference's declared execution-affecting fields remain mandatory. A bounded
rerun follows this changed diagnosis. Earlier evidence is retained as FAIL.
