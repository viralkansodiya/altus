frappe.ui.form.on("Leave Application",{
    custom_leave_primary_approver : frm =>{
        
    },
    setup: function (frm) {
		frm.set_query("custom_leave_primary_approver", function () {
			return {
				query: "altus.altus.docevent.leave_application.get_approvers",
				filters: {
					employee: frm.doc.employee,
					doctype: frm.doc.doctype,
				},
			};
		});

		frm.set_query("employee", erpnext.queries.employee);
	},
})  