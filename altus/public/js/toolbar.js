console.log("h")

frappe.ui.toolbar.Toolbar = class extends frappe.ui.toolbar.Toolbar {
    setup_awesomebar() {
		if (frappe.boot.desk_settings.search_bar) {
			frappe.call({
				method: "altus.api.check_search_bar_per",
				args:{
					user : frappe.session.user
				},
				callback:r=>{
					if(r.message){
						let awesome_bar = new frappe.search.AwesomeBar();
						awesome_bar.setup("#navbar-search");
					}else{
						$("#navbar-search").prop("hidden", true);
					}
				}
			})
			
		}
		if (frappe.model.can_read("RQ Job")) {
			frappe.search.utils.make_function_searchable(function () {
				frappe.set_route("List", "RQ Job");
			}, __("Background Jobs"));
		}
	}
}