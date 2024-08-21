# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_approvers(doctype, txt, searchfield, start, page_len, filters):
	if not filters.get("employee"):
		frappe.throw(_("Please select Employee first."))

	approvers = []
	department_details = {}
	department_list = []
	employee = frappe.get_value(
		"Employee",
		filters.get("employee"),
		["employee_name", "department", "custom_leave_primary_approver", "expense_approver", "shift_request_approver"],
		as_dict=True,
	)

	employee_department = filters.get("department") or employee.department
	if employee_department:
		department_details = frappe.db.get_value(
			"Department", {"name": employee_department}, ["lft", "rgt"], as_dict=True
		)
	if department_details:
		department_list = frappe.db.sql(
			"""select name from `tabDepartment` where lft <= %s
			and rgt >= %s
			and disabled=0
			order by lft desc""",
			(department_details.lft, department_details.rgt),
			as_list=True,
		)

	if filters.get("doctype") == "Leave Application" and employee.custom_leave_primary_approver:
		approvers.append(
			frappe.db.get_value("User", employee.custom_leave_primary_approver, ["name", "first_name", "last_name"])
		)

	if filters.get("doctype") == "Expense Claim" and employee.expense_approver:
		approvers.append(
			frappe.db.get_value("User", employee.expense_approver, ["name", "first_name", "last_name"])
		)

	if filters.get("doctype") == "Shift Request" and employee.shift_request_approver:
		approvers.append(
			frappe.db.get_value("User", employee.shift_request_approver, ["name", "first_name", "last_name"])
		)

	if filters.get("doctype") == "Leave Application":
		parentfield = "leave_approvers"
		field_name = "Leave Primary Approver"
	elif filters.get("doctype") == "Expense Claim":
		parentfield = "expense_approvers"
		field_name = "Expense Approver"
	elif filters.get("doctype") == "Shift Request":
		parentfield = "shift_request_approver"
		field_name = "Shift Request Approver"
	if department_list:
		for d in department_list:
			approvers += frappe.db.sql(
				"""select user.name, user.first_name, user.last_name from
				tabUser user, `tabDepartment Approver` approver where
				approver.parent = %s
				and user.name like %s
				and approver.parentfield = %s
				and approver.approver=user.name""",
				(d, "%" + txt + "%", parentfield),
				as_list=True,
			)

	if len(approvers) == 0:
		error_msg = _("Please set {0} for the Employee: {1}").format(
			frappe.bold(_(field_name)),
			get_link_to_form("Employee", filters.get("employee"), employee.employee_name),
		)
		frappe.throw(error_msg, title=_("{0} Missing").format(_(field_name)))

	return set(tuple(approver) for approver in approvers)


from hrms.hr.doctype.leave_application.leave_application import LeaveApplication
from hrms.hr.utils import (
	get_holiday_dates_for_employee,
	get_leave_period,
	set_employee_name,
	share_doc_with_approver,
	validate_active_employee,
)

class altusLeaveApplication(LeaveApplication):
	def on_update(self):
		if self.status == "Primary Approved":
			self.custom_primary_approved = 1
			if not self.custom_leave_primary_approver:
				frappe.throw("Please set default primary leave approver for employee {0}".format(get_link_to_form("Employee", self.employee)))
			if frappe.session.user != self.custom_leave_primary_approver:
				frappe.throw("Leave Application primary approval only allowed by {0}".format(get_link_to_form("User" , self.custom_leave_primary_approver, frappe.db.get_value("User", self.custom_leave_primary_approver, "full_name"))))
		if self.docstatus < 1:
			# notify leave approver about creation
			if frappe.db.get_single_value("HR Settings", "send_leave_notification"):
				self.notify_leave_approver()
		usr_roles = frappe.get_roles(frappe.session.user)
		if "Supervisor" not in usr_roles or "Manager" not in usr_roles and self.status not in [ "Primary Approved","Approved"]:
			self.share_doc_with_approver(self.custom_leave_primary_approver)
		else:
			share_doc_with_approver(self, self.leave_approver)
	
	def share_doc_with_approver(doc, user):
		if not user:
			return

		# if approver does not have permissions, share
		if not frappe.has_permission(doc=doc, ptype="submit", user=user):
			frappe.share.add_docshare(
				doc.doctype, doc.name, user, submit=0,write=1, flags={"ignore_share_permission": True}
			)

			frappe.msgprint(
				_("Shared with the user {0}").format(user, alert=True)
			)

		# remove shared doc if approver changes
		doc_before_save = doc.get_doc_before_save()
		if doc_before_save:
			approvers = {
				"Leave Application": "leave_approver",
				"Expense Claim": "expense_approver",
				"Shift Request": "approver",
			}

			approver = approvers.get(doc.doctype)
			if doc_before_save.get(approver) != doc.get(approver):
				frappe.share.remove(doc.doctype, doc.name, doc_before_save.get(approver))

	def on_submit(self):
		if self.status in ["Open", "Cancelled", "Primary Approved"]:
			frappe.throw(_("Only Leave Applications with status 'Approved' and 'Rejected' can be submitted"))

		self.validate_back_dated_application()
		self.update_attendance()

		# notify leave applier about approval
		if frappe.db.get_single_value("HR Settings", "send_leave_notification"):
			self.notify_employee()

		self.create_leave_ledger_entry()
		self.reload()
		
	def notify_leave_approver(self):
		if self.custom_leave_primary_approver and not self.custom_primary_approved:
			usr_roles = frappe.get_roles(frappe.session.user)
			if "Supervisor" not in usr_roles or "Manager" not in usr_roles:
				parent_doc = frappe.get_doc("Leave Application", self.name)
				args = parent_doc.as_dict()

				template = frappe.db.get_single_value("HR Settings", "leave_approval_notification_template")
				if not template:
					frappe.msgprint(
						_("Please set default template for Leave Approval Notification in HR Settings.")
					)
					return
				email_template = frappe.get_doc("Email Template", template)
				message = frappe.render_template(email_template.response_, args)

				self.notify(
					{
						# for post in messages
						"message": message,
						"message_to": self.custom_leave_primary_approver,
						# for email
						"subject": email_template.subject,
					}
				)
		if self.leave_approver:
			usr_roles = frappe.get_roles(frappe.session.user)
			if "Supervisor" in usr_roles:
				parent_doc = frappe.get_doc("Leave Application", self.name)
				args = parent_doc.as_dict()

				template = frappe.db.get_single_value("HR Settings", "leave_approval_notification_template")
				if not template:
					frappe.msgprint(
						_("Please set default template for Leave Approval Notification in HR Settings.")
					)
					return
				email_template = frappe.get_doc("Email Template", template)
				message = frappe.render_template(email_template.response_, args)

				self.notify(
					{
						# for post in messages
						"message": message,
						"message_to": self.leave_approver,
						# for email
						"subject": email_template.subject,
					}
				)