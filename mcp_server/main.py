import os
from mcp.server.fastmcp import FastMCP
from data import EMPLOYEES, LAPTOPS

# Get the PORT from Cloud Run (default to 8080)
port = int(os.environ.get("PORT", 8080))

# Pass host and port into the constructor here
mcp = FastMCP("hr-it-tools", host="0.0.0.0", port=port)

@mcp.tool()
def get_employee_info(employee_id: str) -> dict:
    """姓名、部門、入社日を含む従業員の基本情報を取得します"""
    return EMPLOYEES.get(employee_id, {"error": f"従業員 {employee_id} は存在しません"})

@mcp.tool()
def get_available_laptops() -> list[dict]:
    """ステータスが available のすべてのノートパソコンのリストを取得します"""
    return [l for l in LAPTOPS if l["status"] == "available"]

@mcp.tool()
def assign_equipment(employee_id: str, laptop_id: str) -> dict:
    """指定されたノートパソコンを従業員に割り当てます"""
    for laptop in LAPTOPS:
        if laptop["id"] == laptop_id:
            if laptop["status"] != "available":
                return {"success": False, "message": "デバイスは既に使用されています"}
            laptop["status"] = "assigned"
            laptop["assigned_to"] = employee_id
            return {"success": True, "message": f"{laptop_id} を {employee_id} に割り当てました"}
    return {"success": False, "message": f"デバイス {laptop_id} は存在しません"}

if __name__ == "__main__":
    # run() only takes the transport argument in the official SDK
    mcp.run(transport="streamable-http")