import frappe

@frappe.whitelist()
def check_search_bar_per(user):
    roles = frappe.get_roles(user)
    for row in roles:
        role_doc = frappe.db.get_value("Role", row, "search_bar")
        if role_doc:
            return True
    return False