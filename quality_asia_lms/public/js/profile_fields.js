/*
 * QA-15 — add Mobile Number, Address, Resume and a Change Password action to the
 * LMS portal's native "Edit Profile" modal, WITHOUT forking the LMS frontend.
 *
 * The LMS SPA ships read-only on Frappe Cloud, so this script is injected into
 * the SPA shell at serve time (see quality_asia_lms/brand.py). It augments the
 * stock frappe-ui Dialog at runtime.
 *
 * Defensive by design: every step is guarded. If the LMS modal markup changes,
 * our section simply doesn't appear and the stock modal keeps working — nothing
 * breaks (it just needs a post-LMS-upgrade visual check).
 */
(function () {
	"use strict";
	if (window.__qaProfileExtras) return;
	window.__qaProfileExtras = true;

	var BACKEND = "quality_asia_lms.overrides.profile";
	var ALLOWED_RESUME = /\.(pdf|docx?|PDF|DOCX?)$/;
	var MAX_RESUME_MB = 5;

	function csrf() {
		return window.csrf_token || (window.boot && window.boot.csrf_token) || "";
	}

	function api(method, args) {
		var post = !!args;
		return fetch("/api/method/" + method, {
			method: post ? "POST" : "GET",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf() },
			body: post ? JSON.stringify(args) : undefined,
		})
			.then(function (r) { return r.json(); })
			.then(function (d) { return d.message; });
	}

	function uploadResume(file) {
		var fd = new FormData();
		fd.append("file", file, file.name);
		fd.append("is_private", 1);
		return fetch("/api/method/upload_file", {
			method: "POST",
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf() },
			body: fd,
		})
			.then(function (r) { return r.json(); })
			.then(function (d) { return d.message && d.message.file_url; });
	}

	function digits(v) { return (v || "").replace(/\D/g, ""); }
	function validMobile(v) { var d = digits(v); return d.length >= 7 && d.length <= 15; }

	// Find the open "Edit Profile" dialog (frappe-ui teleports it to <body>).
	function findModal() {
		var nodes = document.querySelectorAll('[role="dialog"], .modal, div');
		for (var i = 0; i < nodes.length; i++) {
			var n = nodes[i];
			if (n.dataset && n.dataset.qaScanned === "1") continue;
			if (n.querySelector && n.querySelector(".grid.grid-cols-2")) {
				// confirm it's the profile modal by its title text
				if (/Edit Profile/.test(n.textContent || "")) return n;
			}
		}
		return null;
	}

	function field(labelText, required, control) {
		var wrap = document.createElement("div");
		var label = document.createElement("div");
		label.className = "mb-1.5 text-xs text-ink-gray-5";
		label.textContent = labelText + (required ? " " : "");
		if (required) {
			var star = document.createElement("span");
			star.textContent = "*";
			star.style.color = "#e20a0a";
			label.appendChild(star);
		}
		wrap.appendChild(label);
		wrap.appendChild(control);
		return wrap;
	}

	function inject(modal) {
		try {
			var grid = modal.querySelector(".grid.grid-cols-2");
			if (!grid || modal.querySelector('[data-qa="extras"]')) return;

			// reuse a native input's classes so our controls look like the rest
			var sample = modal.querySelector("input:not([type=file])");
			var inputCls = sample ? sample.className : "w-full rounded border px-2 py-1.5 text-base";

			var block = document.createElement("div");
			block.setAttribute("data-qa", "extras");
			block.className = "mt-6 border-t border-outline-gray-2 pt-4 space-y-4";

			var heading = document.createElement("div");
			heading.className = "text-sm font-semibold text-ink-gray-9";
			heading.textContent = "Contact & Documents";
			block.appendChild(heading);

			// Email (read-only — login id, not editable here)
			var email = document.createElement("input");
			email.type = "email";
			email.className = inputCls;
			email.readOnly = true;
			email.style.opacity = "0.7";
			email.style.cursor = "not-allowed";
			block.appendChild(field("Email ID", true, email));

			// Mobile (required)
			var mobile = document.createElement("input");
			mobile.type = "tel";
			mobile.className = inputCls;
			mobile.placeholder = "Mobile Number";
			block.appendChild(field("Mobile Number", true, mobile));

			var mobileErr = document.createElement("div");
			mobileErr.className = "text-xs";
			mobileErr.style.color = "#e20a0a";
			mobileErr.style.display = "none";
			mobileErr.textContent = "Please enter a valid phone number.";
			block.appendChild(mobileErr);

			// Address (optional)
			var address = document.createElement("textarea");
			address.className = inputCls;
			address.rows = 2;
			address.placeholder = "Address (optional)";
			block.appendChild(field("Address", false, address));

			// Resume (optional, file)
			var resumeUrl = { value: "" };
			var resumeInput = document.createElement("input");
			resumeInput.type = "file";
			resumeInput.accept = ".pdf,.doc,.docx";
			resumeInput.className = "text-sm";
			var resumeStatus = document.createElement("a");
			resumeStatus.className = "text-xs text-ink-blue-link block mt-1";
			resumeStatus.target = "_blank";
			var resumeWrap = field("Resume (PDF/DOC, ≤" + MAX_RESUME_MB + "MB)", false, resumeInput);
			resumeWrap.appendChild(resumeStatus);
			block.appendChild(resumeWrap);

			resumeInput.addEventListener("change", function () {
				var f = resumeInput.files && resumeInput.files[0];
				if (!f) return;
				if (!ALLOWED_RESUME.test(f.name)) { resumeStatus.textContent = "Please upload a PDF or DOC file."; resumeStatus.removeAttribute("href"); return; }
				if (f.size > MAX_RESUME_MB * 1024 * 1024) { resumeStatus.textContent = "This file is too large (max " + MAX_RESUME_MB + " MB)."; resumeStatus.removeAttribute("href"); return; }
				resumeStatus.textContent = "Uploading your file…";
				uploadResume(f).then(function (url) {
					if (url) { resumeUrl.value = url; resumeStatus.textContent = "Uploaded: " + f.name; resumeStatus.href = url; }
					else { resumeStatus.textContent = "Upload didn't work. Please try again."; }
				});
			});

			// Change Password (proper button → native /update-password page)
			var pwd = document.createElement("button");
			pwd.type = "button";
			pwd.textContent = "Change Password";
			pwd.style.cssText =
				"display:inline-flex;align-items:center;padding:6px 14px;border:1px solid #e20a0a;" +
				"border-radius:8px;background:#fff;color:#e20a0a;font-size:13px;font-weight:600;cursor:pointer;";
			pwd.addEventListener("mouseenter", function () { pwd.style.background = "#e20a0a"; pwd.style.color = "#fff"; });
			pwd.addEventListener("mouseleave", function () { pwd.style.background = "#fff"; pwd.style.color = "#e20a0a"; });
			pwd.addEventListener("click", function () { window.location.href = "/update-password"; });
			var pwdWrap = document.createElement("div");
			pwdWrap.className = "pt-1";
			pwdWrap.appendChild(pwd);
			block.appendChild(pwdWrap);

			grid.parentNode.insertBefore(block, grid.nextSibling);

			// pre-fill current values
			api(BACKEND + ".get_profile_extras").then(function (d) {
				if (!d) return;
				email.value = d.email || "";
				mobile.value = d.mobile_no || "";
				address.value = d.address || "";
				if (d.resume) { resumeUrl.value = d.resume; resumeStatus.textContent = "View current resume"; resumeStatus.href = d.resume; }
			});

			// save our fields when the modal's Save button is clicked
			var buttons = modal.querySelectorAll("button");
			for (var i = 0; i < buttons.length; i++) {
				if (/^\s*Save\s*$/.test(buttons[i].textContent || "")) {
					buttons[i].addEventListener("click", function () {
						if (mobile.value && !validMobile(mobile.value)) { mobileErr.style.display = "block"; return; }
						mobileErr.style.display = "none";
						api(BACKEND + ".update_profile_extras", {
							mobile_no: mobile.value || "",
							address: address.value || "",
							resume: resumeUrl.value || "",
						});
					}, false);
					break;
				}
			}
		} catch (e) {
			/* fail-safe: never break the stock modal */
		}
	}

	var observer = new MutationObserver(function () {
		var modal = findModal();
		if (modal) { modal.dataset.qaScanned = "1"; inject(modal); }
	});
	observer.observe(document.body, { childList: true, subtree: true });
})();
