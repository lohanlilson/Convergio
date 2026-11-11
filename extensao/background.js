// Convergio — captura os downloads do navegador e envia para o programa (http://127.0.0.1:47851).
// Se o Convergio não estiver aberto (ou a captura estiver desligada), o navegador baixa normalmente.
const API = "http://127.0.0.1:47851";
const PADRAO = { ativo: true, minimoMB: 1 };

async function config() {
  return Object.assign({}, PADRAO, await chrome.storage.local.get(PADRAO));
}

function navegador() {
  const marcas = (navigator.userAgentData && navigator.userAgentData.brands || []).map(b => b.brand).join(" ");
  if (navigator.brave) return "Brave";
  if (/Edge/i.test(marcas) || /Edg\//.test(navigator.userAgent)) return "Edge";
  if (/Opera/i.test(marcas) || /OPR\//.test(navigator.userAgent)) return "Opera";
  if (/Vivaldi/i.test(navigator.userAgent)) return "Vivaldi";
  return "Chrome";
}

async function chamar(caminho, dados) {
  const opcoes = {
    method: dados ? "POST" : "GET",
    headers: {
      "X-Convergio": "1", "X-Convergio-Navegador": navegador(), "Content-Type": "application/json",
      "X-Convergio-Extensao": chrome.runtime.getManifest().version,
    },
  };
  if (dados) opcoes.body = JSON.stringify(dados);
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 2500);
  try {
    const r = await fetch(API + caminho, { ...opcoes, signal: ctl.signal });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  } finally {
    clearTimeout(t);
  }
}

async function estadoConvergio() {
  const r = await chamar("/ping");
  return r ? { aberto: true, capturar: r.capturar !== false, versao: r.versao } : { aberto: false, capturar: false };
}

async function cookiesPara(url) {
  try {
    const lista = await chrome.cookies.getAll({ url });
    return lista.map(c => `${c.name}=${c.value}`).join("; ");
  } catch (e) {
    return "";
  }
}

function nomeDoArquivo(caminho) {
  return (caminho || "").split(/[\\/]/).pop();
}

async function enviar(url, extra) {
  return chamar("/baixar", {
    url,
    cookies: await cookiesPara(url),
    userAgent: navigator.userAgent,
    navegador: navegador(),
    ...extra,
  });
}

// Downloads iniciados pelo navegador.
// onDeterminingFilename roda ANTES da janela "Salvar como" do navegador: decidimos aqui se o download vai
// para o Convergio (cancela no navegador, sem janela) ou segue normalmente no navegador.
const IGNORAR = "convergio_ignorar";   // links devolvidos ao navegador (não capturar de novo)

async function marcarIgnorar(url) {
  const d = await chrome.storage.session.get({ [IGNORAR]: [] });
  d[IGNORAR].push(url);
  await chrome.storage.session.set({ [IGNORAR]: d[IGNORAR].slice(-20) });
}

async function deveIgnorar(url) {
  const d = await chrome.storage.session.get({ [IGNORAR]: [] });
  const i = d[IGNORAR].indexOf(url);
  if (i < 0) return false;
  d[IGNORAR].splice(i, 1);
  await chrome.storage.session.set({ [IGNORAR]: d[IGNORAR] });
  return true;
}

async function decidir(item) {
  const cfg = await config();
  if (!cfg.ativo) return false;
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url) || item.state !== "in_progress") return false;
  if (item.byExtensionId === chrome.runtime.id || await deveIgnorar(url)) return false;
  if (cfg.minimoMB > 0 && item.totalBytes > 0 && item.totalBytes < cfg.minimoMB * 1024 * 1024) return false;
  const estado = await estadoConvergio();
  if (!estado.aberto || !estado.capturar) return false;

  try { await chrome.downloads.cancel(item.id); } catch (e) { return false; }
  chrome.downloads.erase({ id: item.id }).catch(() => {});
  const ok = await enviar(url, {
    referrer: item.referrer || "",
    nome: nomeDoArquivo(item.filename),
    tamanho: item.totalBytes > 0 ? item.totalBytes : (item.fileSize > 0 ? item.fileSize : null),
    mime: item.mime || "",
  });
  if (!ok) {
    // o Convergio parou de responder: devolve o download ao navegador
    await marcarIgnorar(url);
    chrome.downloads.download({ url }).catch(() => {});
  }
  return true;
}

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  decidir(item)
    .catch(() => false)
    .then((capturado) => { if (!capturado) suggest(); });
  return true;   // vamos responder depois (assíncrono)
});

// avisa o Convergio de que este navegador está vinculado (a cada minuto e ao abrir)
chrome.alarms.create("convergio-ping", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "convergio-ping") chamar("/ping"); });
chrome.runtime.onStartup.addListener(() => chamar("/ping"));
chrome.runtime.onInstalled.addListener(() => chamar("/ping"));
chamar("/ping");

// botão direito num link: "Baixar com o Convergio"
function criarMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "convergio-link", title: "Baixar com o Convergio", contexts: ["link"] });
    chrome.contextMenus.create({ id: "convergio-midia", title: "Baixar com o Convergio", contexts: ["video", "audio", "image"] });
  });
}
chrome.runtime.onInstalled.addListener(criarMenus);
chrome.runtime.onStartup.addListener(criarMenus);

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.srcUrl;
  if (!url || !/^https?:/i.test(url)) return;
  const ok = await enviar(url, { referrer: (tab && tab.url) || info.pageUrl || "" });
  if (!ok) {
    chrome.notifications.create({
      type: "basic", iconUrl: "icones/icone128.png", title: "Convergio não está aberto",
      message: "Abra o Convergio e tente de novo. O download não foi iniciado.",
    });
  }
});

// ---------------------------------------------------------------- vídeos nas páginas
// Observa as respostas de cada aba e guarda os vídeos encontrados: listas de streaming (.m3u8) e arquivos
// de vídeo/áudio diretos. O popup da extensão mostra a lista com o botão "Baixar".
// Não captura YouTube (os termos do serviço não permitem) nem vídeos com proteção contra cópia (DRM).
const SITES_FORA = /(^|\.)(youtube\.com|youtu\.be|googlevideo\.com|youtube-nocookie\.com)$/i;
const TIPOS_LISTA = /mpegurl/i;
const TIPOS_MIDIA = /^(video|audio)\//i;
const PEDACO = /\.(ts|m4s|m4f|aac|vtt|key)(\?|$)/i;

function chaveAba(tabId) { return "midias_" + tabId; }

async function midiasDaAba(tabId) {
  const k = chaveAba(tabId);
  return (await chrome.storage.session.get({ [k]: [] }))[k];
}

async function atualizarSelo(tabId) {
  const n = (await midiasDaAba(tabId)).length;
  chrome.action.setBadgeBackgroundColor({ color: "#6d3cf0" }).catch(() => {});
  chrome.action.setBadgeText({ tabId, text: n ? String(n) : "" }).catch(() => {});
}

async function classificarLista(url) {
  // lista principal (tem as qualidades), lista de uma qualidade, ou transmissão ao vivo
  try {
    const r = await fetch(url, { credentials: "include" });
    if (!r.ok) return { classe: "desconhecida" };
    const t = await r.text();
    if (t.includes("#EXT-X-STREAM-INF")) {
      const filhas = [];
      const linhas = t.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
      linhas.forEach((l, i) => {
        if (l.startsWith("#EXT-X-STREAM-INF") && linhas[i + 1]) filhas.push(new URL(linhas[i + 1], r.url).href);
        const m = l.startsWith("#EXT-X-MEDIA") && l.match(/URI="([^"]+)"/);
        if (m) filhas.push(new URL(m[1], r.url).href);
      });
      const alturas = [...t.matchAll(/RESOLUTION=\d+x(\d+)/g)].map((m) => Number(m[1]));
      return { classe: "principal", filhas, qualidade: alturas.length ? Math.max(...alturas) + "p" : "" };
    }
    if (!t.includes("#EXTINF")) return { classe: "desconhecida" };
    if (!t.includes("#EXT-X-ENDLIST")) return { classe: "ao-vivo" };
    if (/METHOD=(?!NONE|AES-128)/.test(t)) return { classe: "protegida" };
    const dur = [...t.matchAll(/#EXTINF:([\d.]+)/g)].reduce((a, m) => a + Number(m[1]), 0);
    return { classe: "simples", duracao: Math.round(dur) };
  } catch (e) {
    return { classe: "desconhecida" };
  }
}

async function registrarMidia(tabId, item) {
  const k = chaveAba(tabId);
  let lista = await midiasDaAba(tabId);
  if (lista.some((m) => m.url === item.url)) return;
  if (item.tipo === "hls") {
    if (lista.some((m) => (m.filhas || []).includes(item.url))) return;      // qualidade de uma lista já registrada
    const c = await classificarLista(item.url);
    if (c.classe === "ao-vivo" || c.classe === "protegida" || c.classe === "desconhecida") return;
    Object.assign(item, c);
    lista = await midiasDaAba(tabId);
    if (lista.some((m) => m.url === item.url || (m.filhas || []).includes(item.url))) return;
    if (c.classe === "principal") lista = lista.filter((m) => !c.filhas.includes(m.url));
  }
  lista.push(item);
  await chrome.storage.session.set({ [k]: lista.slice(-15) });
  atualizarSelo(tabId);
}

chrome.webRequest.onHeadersReceived.addListener(
  (d) => {
    if (d.tabId < 0 || d.statusCode < 200 || d.statusCode >= 300) return;
    let host = "";
    try { host = new URL(d.url).hostname; } catch (e) { return; }
    if (SITES_FORA.test(host) || (d.initiator && SITES_FORA.test(new URL(d.initiator).hostname))) return;
    const cab = Object.fromEntries((d.responseHeaders || []).map((h) => [h.name.toLowerCase(), h.value || ""]));
    const tipo = cab["content-type"] || "";
    const caminho = d.url.split("?")[0];
    if (TIPOS_LISTA.test(tipo) || /\.m3u8$/i.test(caminho)) {
      registrarMidia(d.tabId, { tipo: "hls", url: d.url });
    } else if (TIPOS_MIDIA.test(tipo) && !/mp2t/i.test(tipo) && !PEDACO.test(d.url)) {
      const total = Number((cab["content-range"] || "").split("/")[1]) || Number(cab["content-length"]) || 0;
      if (total >= 1024 * 1024) registrarMidia(d.tabId, { tipo: "arquivo", url: d.url, tamanho: total, mime: tipo.split(";")[0] });
    }
  },
  { urls: ["http://*/*", "https://*/*"], types: ["xmlhttprequest", "media", "other"] },
  ["responseHeaders"]
);

// página nova na aba: esquece os vídeos da página anterior
chrome.webNavigation.onCommitted.addListener((d) => {
  if (d.frameId === 0 && d.transitionType !== "auto_subframe") {
    chrome.storage.session.remove(chaveAba(d.tabId)).then(() => atualizarSelo(d.tabId));
  }
});
chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(chaveAba(tabId)));

function nomeParaVideo(titulo, item) {
  const base = (titulo || "video").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 100) || "video";
  if (item.tipo === "hls") return base + ".mp4";
  const ext = (item.url.split("?")[0].match(/\.([a-z0-9]{2,4})$/i) || [])[1] || (item.mime || "").split("/")[1] || "mp4";
  return base + "." + ext;
}

async function baixarMidia(item, tab) {
  return enviar(item.url, {
    tipo: item.tipo === "hls" ? "hls" : undefined,
    referrer: (tab && tab.url) || "",
    nome: nomeParaVideo(tab && tab.title, item),
    tamanho: item.tamanho || null,
  });
}

chrome.runtime.onMessage.addListener((msg, remetente, responder) => {
  if (msg && msg.acao === "baixar-midia") {
    chrome.tabs.get(msg.tabId).then((tab) => baixarMidia(msg.item, tab)).then((r) => responder({ ok: !!r }))
      .catch(() => responder({ ok: false }));
    return true;
  }
});
