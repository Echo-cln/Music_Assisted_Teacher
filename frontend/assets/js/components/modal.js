export function showModal(content) {
  const root = document.getElementById("modalRoot");
  root.innerHTML = `<div class="modal-backdrop"><div class="modal">${content}</div></div>`;
  root.querySelectorAll("[data-close]").forEach(button => button.onclick = () => {
    root.innerHTML = "";
  });
  return root;
}

