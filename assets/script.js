(() => {
  const year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();

  const menuButton = document.querySelector(".menu-toggle");
  const nav = document.getElementById("main-nav");
  if (menuButton && nav) {
    menuButton.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      menuButton.setAttribute("aria-expanded", String(open));
    });
    nav.querySelectorAll("a").forEach(link => link.addEventListener("click", () => {
      nav.classList.remove("open");
      menuButton.setAttribute("aria-expanded", "false");
    }));
  }

  const search = document.getElementById("tool-search");
  const cards = [...document.querySelectorAll(".directory-card")];
  const filters = [...document.querySelectorAll("[data-filter]")];
  const count = document.getElementById("result-count");
  const empty = document.getElementById("empty-state");
  let activeFilter = "all";
  const applyFilter = () => {
    if (!cards.length) return;
    const term = (search?.value || "").trim().toLowerCase();
    let visible = 0;
    cards.forEach(card => {
      const kind = card.dataset.kind || "";
      const categories = card.dataset.category || "";
      const haystack = `${card.dataset.search || ""} ${card.innerText}`.toLowerCase();
      const filterMatch = activeFilter === "all" ||
        (activeFilter === "internal" && kind === "internal") ||
        (activeFilter === "external" && kind === "external") ||
        categories.split(/\s+/).includes(activeFilter);
      const matches = filterMatch && haystack.includes(term);
      card.hidden = !matches;
      if (matches) visible++;
    });
    if (count) count.textContent = `Showing ${visible} ${visible === 1 ? "listing" : "listings"}`;
    if (empty) empty.hidden = visible !== 0;
  };
  if (search) search.addEventListener("input", applyFilter);
  filters.forEach(button => button.addEventListener("click", () => {
    activeFilter = button.dataset.filter || "all";
    filters.forEach(item => item.classList.toggle("active", item === button));
    applyFilter();
  }));
  document.addEventListener("keydown", event => {
    if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      if (search) { event.preventDefault(); search.focus(); }
    }
    if (event.key === "Escape" && search && document.activeElement === search) search.blur();
  });
  applyFilter();
})();