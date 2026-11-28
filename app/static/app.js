// 화면 공용 동작 (서버 검증과 별개로 입력 편의만 담당)
document.addEventListener("click", (e) => {
  // 확인 대화상자 열기/닫기: <button data-open="dialogId">, <button data-close>
  const opener = e.target.closest("[data-open]");
  if (opener) {
    const dlg = document.getElementById(opener.dataset.open);
    if (dlg) dlg.showModal();
  }
  if (e.target.closest("[data-close]")) e.target.closest("dialog")?.close();

  // 표 행 펼치기: <button class="toggle" data-target="rowId">
  const tg = e.target.closest(".toggle[data-target]");
  if (tg) {
    const row = document.getElementById(tg.dataset.target);
    row.hidden = !row.hidden;
    tg.setAttribute("aria-expanded", String(!row.hidden));
  }

  // 입고: 같은 상품의 소비기한 추가 줄 (<template id="..."> 복제) / 줄 삭제
  const add = e.target.closest("[data-add-line]");
  if (add) {
    const tpl = document.getElementById(add.dataset.addLine);
    add.closest(".rc-lines").querySelector(".rc-subs").appendChild(tpl.content.cloneNode(true));
    recalcReceipt();
  }
  const rm = e.target.closest("[data-remove-line]");
  if (rm) { rm.closest(".rc-line").remove(); recalcReceipt(); }
});

// 정상수량 = 입고수량 − 파손수량 자동 계산 + 입고 합계 표시
function recalcReceipt() {
  let recv = 0, dmg = 0;
  document.querySelectorAll(".rc-line").forEach((line) => {
    const r = parseInt(line.querySelector("[name='recv[]']")?.value) || 0;
    const d = parseInt(line.querySelector("[name='dmg[]']")?.value) || 0;
    const out = line.querySelector(".normal");
    if (out) out.value = r - d;
    recv += r; dmg += d;
  });
  const sum = document.getElementById("rc-sum");
  if (sum) sum.textContent = `입고 ${recv}개 · 파손 ${dmg}개 · 정상 ${recv - dmg}개`;
}

document.addEventListener("input", (e) => {
  if (e.target.closest(".rc-line")) recalcReceipt();
  // 재고 조정: 차이 = 실제 수량 − 장부 수량
  const adj = e.target.closest("form[data-adjust]");
  if (adj) {
    const before = parseInt(adj.dataset.before) || 0;
    const after = parseInt(adj.querySelector("[name=after_qty]").value);
    const note = adj.querySelector(".after-note");
    if (isNaN(after)) { adj.querySelector(".diff").value = ""; note.textContent = ""; return; }
    const diff = after - before;
    adj.querySelector(".diff").value = `${diff > 0 ? "+" : ""}${diff}개`;
    note.textContent = `조정 후 이 입고 묶음의 재고는 ${after}개입니다. 차이 ${diff > 0 ? "+" : ""}${diff}개가 재고 이력에 기록됩니다.`;
  }
});

// 판매: F8 = 판매 완료 (INT-003)
document.addEventListener("keydown", (e) => {
  if (e.key === "F8") {
    const btn = document.getElementById("complete-sale");
    if (btn) { e.preventDefault(); btn.click(); }
  }
});

window.addEventListener("load", () => {
  document.querySelector("[autofocus]")?.focus();
  recalcReceipt();
});
