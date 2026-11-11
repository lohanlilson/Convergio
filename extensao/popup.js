const PADRAO = { ativo: true, minimoMB: 1 };
const $ = (id) => document.getElementById(id);

async function iniciar() {
  const cfg = Object.assign({}, PADRAO, await chrome.storage.local.get(PADRAO));
  $("ativo").checked = cfg.ativo;
  $("minimo").value = cfg.minimoMB;
  $("ativo").addEventListener("change", () => chrome.storage.local.set({ ativo: $("ativo").checked }));
  $("minimo").addEventListener("change", () =>
    chrome.storage.local.set({ minimoMB: Math.max(0, Number($("minimo").value) || 0) }));

  const st = $("status");
  try {
    const r = await fetch("http://127.0.0.1:47851/ping", { headers: { "X-Convergio": "1" } });
    const d = await r.json();
    st.textContent = d.capturar === false
      ? `Conectado (v${d.versao}) — captura desligada no programa`
      : `Conectado ao Convergio ${d.versao}`;
    st.className = "status ok";
  } catch (e) {
    st.textContent = "Convergio não está aberto — o navegador baixa normalmente";
    st.className = "status erro";
  }
}
iniciar();
