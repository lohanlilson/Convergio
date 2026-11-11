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
    const r = await fetch("http://127.0.0.1:47851/ping", { headers: { "X-Convergio": "1", "X-Convergio-Extensao": chrome.runtime.getManifest().version } });
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

function tamanho(b) {
  return b >= 1 << 30 ? (b / (1 << 30)).toFixed(2) + " GB" : (b / (1 << 20)).toFixed(1) + " MB";
}

function duracao(s) {
  const m = Math.floor(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}min` : `${m}min ${s % 60}s`;
}

async function listarVideos() {
  const parametro = Number(new URLSearchParams(location.search).get("tabId"));      // usado nos testes
  const tabId = parametro || (await chrome.tabs.query({ active: true, currentWindow: true }))[0]?.id;
  if (!tabId) return;
  const k = "midias_" + tabId;
  const lista = (await chrome.storage.session.get({ [k]: [] }))[k];
  if (!lista.length) return;
  $("videos").hidden = false;
  for (const item of lista) {
    const li = document.createElement("li");
    const div = document.createElement("div");
    const nome = document.createElement("div");
    nome.className = "nome";
    nome.textContent = item.tipo === "hls" ? "Vídeo (streaming)" : decodeURIComponent(item.url.split("?")[0].split("/").pop() || "vídeo");
    const det = document.createElement("div");
    det.className = "det";
    det.textContent = item.tipo === "hls"
      ? [item.qualidade, item.duracao ? duracao(item.duracao) : "", new URL(item.url).hostname].filter(Boolean).join(" · ")
      : [tamanho(item.tamanho), item.mime].filter(Boolean).join(" · ");
    div.append(nome, det);
    const bt = document.createElement("button");
    bt.textContent = "Baixar";
    bt.addEventListener("click", async () => {
      bt.disabled = true;
      const r = await chrome.runtime.sendMessage({ acao: "baixar-midia", tabId, item });
      bt.textContent = r && r.ok ? "Enviado ✓" : "Abra o Convergio";
      if (!(r && r.ok)) bt.disabled = false;
    });
    li.append(div, bt);
    $("lista").append(li);
  }
}

iniciar();
listarVideos();
