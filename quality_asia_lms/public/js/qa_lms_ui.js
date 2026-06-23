/*
 * QA LMS UI enhancements — runtime DOM patches for the upstream LMS Vue SPA.
 *
 * Injected via quality_asia_lms/brand.py (after_request). Uses a
 * MutationObserver on document.body — the same proven pattern as
 * profile_fields.js — to detect and modify upstream-rendered DOM without
 * forking the LMS frontend.
 *
 * Three concerns:
 *   1. Remove GST / PAN / "Where did you hear" / Coupon from the billing page
 *   2. Auto-redirect logged-out users from billing to /login
 *   3. Replace the confusing "0 out of 0" quiz summary for ungraded quizzes
 */
(function () {
	"use strict";
	if (window.__qaLmsUI) return;
	window.__qaLmsUI = true;

	/* ------------------------------------------------------------------ */
	/* Helpers                                                             */
	/* ------------------------------------------------------------------ */

	function isBillingPage() {
		return /\/billing\//.test(window.location.pathname);
	}

	/**
	 * Walk up from a node to find its nearest form-field wrapper.
	 * The LMS billing form wraps each <FormControl>/<Link> in a <div> whose
	 * first child is a label <span>/<div> — we remove the entire wrapper.
	 */
	function fieldWrapperByLabel(root, labelText) {
		var labels = root.querySelectorAll("label, span, div");
		for (var i = 0; i < labels.length; i++) {
			var el = labels[i];
			var text = (el.textContent || "").trim();
			if (text === labelText || text === labelText + " *" || text.startsWith(labelText)) {
				// Walk up at most 3 levels to find the field wrapper
				var wrapper = el.parentElement;
				if (wrapper && wrapper.parentElement) {
					// If the wrapper's parent is the grid, the wrapper IS the field container
					var grid = root.querySelector(".grid");
					if (grid && grid.contains(wrapper)) {
						return wrapper;
					}
					// Otherwise try one more level
					if (wrapper.parentElement && grid && grid.contains(wrapper.parentElement)) {
						return wrapper.parentElement;
					}
					return wrapper;
				}
			}
		}
		return null;
	}

	/* ------------------------------------------------------------------ */
	/* Item 3 — Remove billing fields                                     */
	/* ------------------------------------------------------------------ */

	var billingCleaned = false;

	function cleanBillingFields() {
		if (billingCleaned || !isBillingPage()) return;

		var main = document.querySelector("main") || document.body;

		// The billing form contains these labels — remove their wrappers
		var labelsToRemove = ["GST Number", "PAN Number", "Where did you hear about us?"];
		var removed = 0;

		for (var i = 0; i < labelsToRemove.length; i++) {
			var wrapper = fieldWrapperByLabel(main, labelsToRemove[i]);
			if (wrapper) {
				wrapper.remove();
				removed++;
			}
		}

		// Remove the coupon code block — it's a self-contained div with "Enter a Coupon Code"
		var allDivs = main.querySelectorAll("div");
		for (var j = 0; j < allDivs.length; j++) {
			var d = allDivs[j];
			if (/Enter a Coupon Code/i.test(d.textContent || "")) {
				// Find the outermost coupon container (has bg-surface-gray-2 class)
				if (d.classList && d.classList.contains("bg-surface-gray-2")) {
					d.remove();
					removed++;
					break;
				}
				// Or if the text is inside a span, walk up to the bg-surface-gray-2 wrapper
				var parent = d;
				for (var k = 0; k < 4; k++) {
					parent = parent.parentElement;
					if (!parent) break;
					if (parent.classList && parent.classList.contains("bg-surface-gray-2")) {
						parent.remove();
						removed++;
						break;
					}
				}
				if (removed > 3) break;
			}
		}

		// Also hide the GST Amount line in the order summary sidebar
		var summaryLabels = main.querySelectorAll("span, div");
		for (var s = 0; s < summaryLabels.length; s++) {
			var txt = (summaryLabels[s].textContent || "").trim().toUpperCase();
			if (txt === "GST AMOUNT:" || txt === "GST AMOUNT") {
				// Walk up to the row container and hide it
				var row = summaryLabels[s].parentElement;
				if (row) row.style.display = "none";
			}
		}

		if (removed > 0) billingCleaned = true;
	}

	/* ------------------------------------------------------------------ */
	/* Item 4 — Guest checkout auto-redirect                              */
	/* ------------------------------------------------------------------ */

	var redirected = false;

	function autoRedirectGuest() {
		if (redirected || !isBillingPage()) return;

		// Detect the NotPermitted card — it has the text "Please login to access this page"
		var cards = document.querySelectorAll("div, p, span");
		for (var i = 0; i < cards.length; i++) {
			var text = (cards[i].textContent || "").trim();
			if (text === "Please login to access this page." || text === "Please login to access this page") {
				// Find the associated login button/link — it's a sibling or nearby <a>/<button>
				var container = cards[i].closest("div.border, div.rounded-lg, div[class]") || cards[i].parentElement;
				if (!container) continue;

				var link = container.querySelector("a[href*='/login'], button");
				if (link) {
					redirected = true;
					var href = link.getAttribute("href") || link.dataset.href;
					if (href && href.indexOf("/login") !== -1) {
						window.location.href = href;
					} else {
						// Construct the redirect URL manually
						window.location.href = "/login?redirect-to=" + encodeURIComponent(window.location.pathname);
					}
					return;
				}

				// Fallback — redirect directly
				redirected = true;
				window.location.href = "/login?redirect-to=" + encodeURIComponent(window.location.pathname);
				return;
			}
		}
	}

	/* ------------------------------------------------------------------ */
	/* Item 5 — Friendly quiz summary for ungraded quizzes                */
	/* ------------------------------------------------------------------ */

	function fixQuizSummary() {
		// Find the "Quiz Summary" heading
		var headings = document.querySelectorAll("div.font-semibold, div.text-lg");
		for (var i = 0; i < headings.length; i++) {
			var h = headings[i];
			if ((h.textContent || "").trim() !== "Quiz Summary") continue;

			var panel = h.parentElement;
			if (!panel || panel.dataset.qaScanned === "1") continue;
			panel.dataset.qaScanned = "1";

			// Look for the score sibling — it contains "out of N"
			var siblings = panel.children;
			for (var j = 0; j < siblings.length; j++) {
				var sib = siblings[j];
				if (sib === h) continue;
				var sibText = (sib.textContent || "").trim();

				// Detect ungraded quiz: "out of 0" means no gradable marks
				var match = sibText.match(/out of (\d+)/);
				if (match && match[1] === "0") {
					// Hide the stock score message
					sib.style.display = "none";

					// Insert a friendly QA-owned message (sibling, not mutation of
					// Vue-managed text, so Vue re-renders can't clobber it)
					var msg = document.createElement("div");
					msg.className = sib.className;
					msg.setAttribute("data-qa", "feedback-thanks");
					msg.textContent = "Thank you! Your responses have been recorded successfully.";
					panel.insertBefore(msg, sib.nextSibling);
					return;
				}
			}
		}
	}

	/* ------------------------------------------------------------------ */
	/* Observer — single watcher for all three concerns                   */
	/* ------------------------------------------------------------------ */

	var observer = new MutationObserver(function () {
		try {
			if (isBillingPage()) {
				autoRedirectGuest();
				cleanBillingFields();
			}
			fixQuizSummary();
		} catch (e) {
			/* fail-safe: never break the stock pages */
		}
	});
	observer.observe(document.body, { childList: true, subtree: true });

	// Also run once immediately for content already rendered
	try {
		if (isBillingPage()) {
			autoRedirectGuest();
			cleanBillingFields();
		}
		fixQuizSummary();
	} catch (e) {
		/* fail-safe */
	}
})();
