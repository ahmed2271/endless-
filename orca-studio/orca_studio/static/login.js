document.getElementById("f").addEventListener("submit", async e => {
  e.preventDefault();
  const r = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({password: document.getElementById("pw").value})});
  if (r.ok) location.href = "/";
  else { const el = document.getElementById("err"); el.textContent = "Wrong password"; el.classList.remove("hidden"); }
});
