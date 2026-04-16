// Lab artifact helpers
function renderLabArtifact(artifact) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="card-title">${artifact.filename}</div>
    <iframe class="lab-frame"
      srcdoc="${artifact.html_content.replace(/"/g,'&quot;')}"
      sandbox="allow-scripts allow-same-origin"
      loading="lazy"></iframe>`;
  return card;
}
