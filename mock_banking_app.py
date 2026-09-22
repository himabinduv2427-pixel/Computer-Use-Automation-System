"""
Mock banking application for testing the automation system.
Simulates a simple back-office app without exposing real credentials.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI(title="Mock Banking App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Mock data
MOCK_MEMBERS = {
    "12345": {
        "name": "John Doe",
        "email": "john@example.com",
        "accounts": {
            "savings": {"type": "Savings", "balance": "$5,234.56"},
            "checking": {"type": "Checking", "balance": "$1,050.00"}
        }
    },
    "67890": {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "accounts": {
            "savings": {"type": "Savings", "balance": "$12,890.00"},
            "checking": {"type": "Checking", "balance": "$3,200.50"}
        }
    }
}

# Session state
current_session = {
    "logged_in": True,
    "current_page": "dashboard",
    "searched_member": None,
    "member_details_open": False
}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard home page"""
    current_session["current_page"] = "dashboard"
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Banking Dashboard</title>
        <style>
            body { font-family: Arial; margin: 20px; background: #f5f5f5; }
            .navbar { background: #003366; color: white; padding: 15px; margin-bottom: 20px; }
            .navbar h1 { margin: 0; }
            .container { max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; }
            button { background: #0066cc; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 3px; }
            button:hover { background: #0052a3; }
            .member-search { margin: 20px 0; }
            input { padding: 10px; width: 300px; border: 1px solid #ddd; border-radius: 3px; }
            .error { color: red; padding: 10px; margin: 10px 0; }
            .success { color: green; padding: 10px; margin: 10px 0; }
            .member-details { margin-top: 30px; padding: 20px; background: #f9f9f9; border-left: 4px solid #0066cc; }
            .account-row { margin: 10px 0; padding: 10px; background: white; border: 1px solid #e0e0e0; }
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1>🏦 Banking Back-Office System</h1>
        </div>

        <div class="container">
            <h2>Member Search</h2>
            <div class="member-search">
                <input type="text" id="member-id-input" placeholder="Enter Member ID" />
                <button id="search-btn" onclick="searchMember()">Search</button>
            </div>

            <div id="search-results"></div>
            <div id="member-detail"></div>
        </div>

        <script>
            async function searchMember() {
                const memberId = document.getElementById('member-id-input').value;
                if (!memberId) {
                    document.getElementById('search-results').innerHTML = '<div class="error">Please enter a member ID</div>';
                    return;
                }

                try {
                    const resp = await fetch('/api/member/' + memberId);
                    const data = await resp.json();

                    if (data.success) {
                        document.getElementById('search-results').innerHTML =
                            '<div class="success">Member found: ' + data.member.name + '</div>' +
                            '<button onclick="viewDetails(' + memberId + ')">View Details</button>';
                    } else {
                        document.getElementById('search-results').innerHTML = '<div class="error">' + data.error + '</div>';
                        document.getElementById('member-detail').innerHTML = '';
                    }
                } catch (e) {
                    document.getElementById('search-results').innerHTML = '<div class="error">Error: ' + e + '</div>';
                }
            }

            async function viewDetails(memberId) {
                try {
                    const resp = await fetch('/api/member/' + memberId);
                    const data = await resp.json();

                    if (data.success) {
                        const member = data.member;
                        let html = '<div class="member-details">';
                        html += '<h3>' + member.name + '</h3>';
                        html += '<p>Email: ' + member.email + '</p>';
                        html += '<h4>Accounts</h4>';
                        for (const [key, account] of Object.entries(member.accounts)) {
                            html += '<div class="account-row">';
                            html += '<strong>' + account.type + '</strong>: ' + account.balance;
                            html += '</div>';
                        }
                        html += '</div>';
                        document.getElementById('member-detail').innerHTML = html;
                    }
                } catch (e) {
                    document.getElementById('member-detail').innerHTML = '<div class="error">Error loading details: ' + e + '</div>';
                }
            }

            // Allow Enter key to search
            document.getElementById('member-id-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') searchMember();
            });
        </script>
    </body>
    </html>
    """


@app.get("/api/member/{member_id}")
async def get_member(member_id: str):
    """API endpoint to get member details"""
    if member_id in MOCK_MEMBERS:
        return {
            "success": True,
            "member": MOCK_MEMBERS[member_id]
        }
    else:
        return {
            "success": False,
            "error": f"Member {member_id} not found in system"
        }


@app.get("/api/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "mock-banking-app",
        "members_available": list(MOCK_MEMBERS.keys())
    }


if __name__ == "__main__":
    import uvicorn
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║  Mock Banking Back-Office Application                      ║
    ║  For testing automation discovery                           ║
    ╚════════════════════════════════════════════════════════════╝

    Server: http://localhost:8001
    Test Members: 12345, 67890

    Example goal: "Look up member 12345 and read their savings balance"
    """)

    uvicorn.run(app, host="0.0.0.0", port=8001)
