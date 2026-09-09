"""In-memory stand-in for a core-banking member file. Fictional only."""

MEMBERS = {
    "12345": {
        "member_id": "12345",
        "name": "Jane Alvarez",
        "status": "active",
        "branch": "Westlake",
        "savings_balance": "4250.17",
        "checking_balance": "890.03",
        "savings_mask": "****8812",
        "checking_mask": "****1109",
    },
    "22222": {
        "member_id": "22222",
        "name": "Marcus Chen",
        "status": "restricted",
        "branch": "Midtown",
        "savings_balance": "110.00",
        "checking_balance": "40.12",
        "savings_mask": "****4401",
        "checking_mask": "****7720",
        "restriction": "Servicing hold — inquiry only. Monetary actions denied.",
    },
}


def lookup(member_id: str) -> dict | None:
    return MEMBERS.get(member_id.strip())
