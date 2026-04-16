// Wiki rendering helpers
function renderWikibooks(html) {
  const div = document.createElement("div");
  div.className = "wikibooks";
  div.innerHTML = html;
  return div;
}
