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

// downloads iniciados pelo navegador
chrome.downloads.onCreated.addListener(async (item) => {
  const cfg = await config();
  if (!cfg.ativo) return;
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url) || item.state !== "in_progress") return;
  if (cfg.minimoMB > 0 && item.totalBytes > 0 && item.totalBytes < cfg.minimoMB * 1024 * 1024) return;

  try { await chrome.downloads.pause(item.id); } catch (e) { /* ainda não começou */ }
  const estado = await estadoConvergio();
  if (!estado.aberto || !estado.capturar) {
    chrome.downloads.resume(item.id).catch(() => {});
    return;
  }
  const ok = await enviar(url, {
    referrer: item.referrer || "",
    nome: nomeDoArquivo(item.filename),
    tamanho: item.totalBytes > 0 ? item.totalBytes : null,
    mime: item.mime || "",
  });
  if (ok) {
    try { await chrome.downloads.cancel(item.id); } catch (e) {}
    try { await chrome.downloads.erase({ id: item.id }); } catch (e) {}
  } else {
    chrome.downloads.resume(item.id).catch(() => {});
  }
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
