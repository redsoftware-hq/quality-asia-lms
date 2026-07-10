/*
 * QA LMS UI enhancements — runtime DOM patches for the upstream LMS Vue SPA.
 *
 * Injected via quality_asia_lms/brand.py (after_request). Uses a
 * MutationObserver on document.body — the same proven pattern as
 * profile_fields.js — to detect and modify upstream-rendered DOM without
 * forking the LMS frontend.
 *
 * Concerns:
 *   1. Remove GST / PAN / "Where did you hear" / Country / Coupon from billing
 *   2. Auto-redirect logged-out users from billing to /login
 *   3. Mask the transient "Not Permitted" card on billing (all connections)
 *   4. Replace the confusing "0 out of 0" quiz summary for ungraded quizzes
 *   5. Replace upstream "Not Permitted" text with friendlier wording everywhere
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

	function getCookie(name) {
		var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
		return m ? decodeURIComponent(m[1]) : null;
	}

	function isGuest() {
		var uid = getCookie("user_id");
		return !uid || uid === "Guest";
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
	/* Item 1 — Early CSS mask for the "Not Permitted" card on billing    */
	/*                                                                    */
	/* This script is <script defer> in <head>, so it runs BEFORE the Vue */
	/* SPA paints. Injecting a <style> here hides the NotPermitted card   */
	/* before it ever becomes visible, preventing the flash on all speeds.*/
	/* ------------------------------------------------------------------ */

	var billingMaskId = "qa-billing-mask";
	var maskTimerId = null;

	function injectBillingMask() {
		if (!isBillingPage()) return;
		if (document.getElementById(billingMaskId)) return;

		var style = document.createElement("style");
		style.id = billingMaskId;
		style.textContent =
			/* Hide the NotPermitted card (div.rounded-md.border...my-32) */
			"div.mx-auto.my-32.rounded-md.border { display: none !important; }" +
			/* Show a centered loader in its place */
			"body.qa-billing-loading main::after {" +
			"  content: ''; display: block; width: 2rem; height: 2rem;" +
			"  margin: 8rem auto; border: 3px solid #e5e7eb;" +
			"  border-top-color: #6b7280; border-radius: 50%;" +
			"  animation: qa-spin 0.7s linear infinite;" +
			"}" +
			"@keyframes qa-spin { to { transform: rotate(360deg); } }";
		document.head.appendChild(style);
		document.body.classList.add("qa-billing-loading");

		// Timeout fallback: if the card is still present after 5s (genuine
		// denial), unmask it so the user is not stuck on a spinner forever.
		maskTimerId = setTimeout(function () {
			removeBillingMask();
			// Run the friendly text replacement for genuine denial cards
			friendlyNotPermitted();
		}, 5000);
	}

	function removeBillingMask() {
		var mask = document.getElementById(billingMaskId);
		if (mask) mask.remove();
		document.body.classList.remove("qa-billing-loading");
		if (maskTimerId) {
			clearTimeout(maskTimerId);
			maskTimerId = null;
		}
	}

	// Inject the mask immediately — runs before SPA paint
	injectBillingMask();

	/* ------------------------------------------------------------------ */
	/* Item 2 — Remove billing fields                                     */
	/* ------------------------------------------------------------------ */

	var billingCleaned = false;

	function cleanBillingFields() {
		if (billingCleaned || !isBillingPage()) return;

		var main = document.querySelector("main") || document.body;

		// The billing form contains these labels — remove their wrappers.
		// Country is hidden because the app forces India server-side via a
		// Property Setter default + payments.py override.
		var labelsToRemove = ["GST Number", "PAN Number", "Where did you hear about us?", "Country"];
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
				if (removed > 4) break;
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

		if (removed > 0) {
			billingCleaned = true;
			// The billing form is now visible — remove the mask/loader
			removeBillingMask();
		}
	}

	/* ------------------------------------------------------------------ */
	/* Item 3 — Guest checkout auto-redirect                              */
	/* ------------------------------------------------------------------ */

	var redirected = false;

	function autoRedirectGuest() {
		if (redirected || !isBillingPage()) return;

		if (isGuest()) {
			redirected = true;
			window.location.href = "/login?redirect-to=" + encodeURIComponent(window.location.pathname);
			return;
		}
	}

	/* ------------------------------------------------------------------ */
	/* Item 4 — Friendly quiz summary for ungraded quizzes                */
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
	/* Item 5 — Friendly "Not Permitted" page text                        */
	/*                                                                    */
	/* Rewrites both NotPermitted.vue and NoPermission.vue card variants. */
	/* Uses per-node data-qa-patched flag instead of a global latch so    */
	/* Vue re-renders get re-patched. Matches with indexOf for tolerance. */
	/* ------------------------------------------------------------------ */

	var NOT_PERMITTED_STRINGS = ["Not Permitted"];
	var BODY_STRINGS = [
		"You are not permitted to access this page.",
		"Please login to access this page.",
		"You do not have permission to access this page.",
	];

	function friendlyNotPermitted() {
		var headings = document.querySelectorAll("h1, h2, h3, div, span");
		for (var i = 0; i < headings.length; i++) {
			var el = headings[i];
			if (el.dataset.qaPatched === "1") continue;

			// Get only the direct text content (ignore child element text)
			var directText = "";
			for (var n = 0; n < el.childNodes.length; n++) {
				if (el.childNodes[n].nodeType === 3) {
					directText += el.childNodes[n].textContent;
				}
			}
			directText = directText.trim();

			var isTitle = false;
			for (var t = 0; t < NOT_PERMITTED_STRINGS.length; t++) {
				if (directText === NOT_PERMITTED_STRINGS[t]) {
					isTitle = true;
					break;
				}
			}
			if (!isTitle) continue;

			// Replace the title text node(s) — preserve child elements (red dot span)
			for (var c = 0; c < el.childNodes.length; c++) {
				if (el.childNodes[c].nodeType === 3 && el.childNodes[c].textContent.trim()) {
					el.childNodes[c].textContent = el.childNodes[c].textContent.replace("Not Permitted", "Login Required");
				}
			}
			el.dataset.qaPatched = "1";

			// Find and replace the body text in the parent container
			var container = el.closest("div.border, div.rounded-md") || el.parentElement;
			if (!container) continue;

			var children = container.querySelectorAll("p, div, span");
			for (var j = 0; j < children.length; j++) {
				var child = children[j];
				var ct = (child.textContent || "").trim();
				for (var b = 0; b < BODY_STRINGS.length; b++) {
					if (ct.indexOf(BODY_STRINGS[b]) !== -1) {
						child.textContent = "Please log in to continue.";
						child.dataset.qaPatched = "1";
						break;
					}
				}
			}
		}
	}

	/* ------------------------------------------------------------------ */
	/* Observer — single watcher for all concerns                         */
	/* ------------------------------------------------------------------ */

	var observer = new MutationObserver(function () {
		try {
			if (isBillingPage()) {
				autoRedirectGuest();
				cleanBillingFields();
			}
			fixQuizSummary();
			friendlyNotPermitted();
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
		friendlyNotPermitted();
	} catch (e) {
		/* fail-safe */
	}
})();
