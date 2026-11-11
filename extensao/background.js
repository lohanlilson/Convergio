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
    headers: { "X-Convergio": "1", "X-Convergio-Navegador": navegador(), "Content-Type": "application/json" },
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
