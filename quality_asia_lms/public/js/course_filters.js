/*
 * QA-39 — Fix the category filter "clear" on /lms/courses WITHOUT forking
 * the LMS frontend.
 *
 * Problem: the upstream Courses.vue category dropdown's first option has an
 * empty label ({label:'', value:null}), making it invisible in the <select>.
 * Users who pick a category (e.g. ?category=Free) can never get back to "All
 * Courses" without hand-editing the URL.
 *
 * Fix: a MutationObserver (same pattern as profile_fields.js) finds the
 * category <select> after the Vue SPA renders and:
 *   1. Relabels the blank first <option> to "All Courses"
 *   2. On selection of that option, hard-navigates to /lms/courses (dropping
 *      the ?category= param). A full navigation sidesteps the compiled Vue
 *      Select's '' vs null ambiguity — bulletproof and zero coupling to Vue
 *      internals.
 *
 * Defensive: fails silently if the LMS markup changes — the stock dropdown
 * keeps working, it just won't have the "All Courses" label.
 */
(function () {
	"use strict";
	if (window.__qaCourseFilters) return;
	window.__qaCourseFilters = true;

	/**
	 * Return the LMS base path (usually "/lms") by stripping query + hash from
	 * the current courses URL, so we don't hard-code the path prefix.
	 */
	function coursesBase() {
		return location.pathname;
	}

	function patchSelect(select) {
		if (!select || select.dataset.qaCoursePatched) return;
		select.dataset.qaCoursePatched = "1";

		// The first <option> is the blank "all" placeholder — give it a label.
		var first = select.options[0];
		if (first && !first.textContent.trim()) {
			first.textContent = "All Courses";
		}

		select.addEventListener("change", function () {
			// When the user picks the blank/All option, hard-navigate to drop
			// the ?category= query param. Non-blank picks are left to Vue.
			if (!select.value) {
				window.location.assign(coursesBase());
			}
		});
	}

	function scan() {
		// Only act on the courses listing route.
		if (!/\/lms\/courses\b/.test(location.pathname)) return;

		try {
			var selects = document.querySelectorAll("select");
			for (var i = 0; i < selects.length; i++) {
				var s = selects[i];
				if (s.dataset.qaCoursePatched) continue;
				// Identify the category dropdown: its first option is the blank
				// placeholder and at least one other option exists.
				if (s.options.length > 1 && s.options[0].value === "") {
					patchSelect(s);
				}
			}
		} catch (e) {
			/* fail-safe: never break the page */
		}
	}

	var observer = new MutationObserver(scan);
	observer.observe(document.body, { childList: true, subtree: true });

	// Also run once now in case the DOM is already rendered.
	scan();
})();
