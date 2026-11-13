#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_map_page.py  --  the map viewer page (HTML, CSS and JavaScript)
#
#  mohaa_map_view.py fills in the __TOKENS__ and writes the result as one
#  self-contained .html file. Everything the page does happens in here:
#
#    readMap / buildScene   read the .map text and build every brush, patch and
#                           terrain block (the part between CORE-BEGIN and CORE-END
#                           has no page or WebGL code, so it can be tested alone)
#    WebGL                  draws the world, models and entity markers, and picks
#                           what is under the mouse by drawing ids into one pixel
#    cameras                Free-look (as the model viewer) and Radiant-look
#                           (MOHRadiant's camera keys and right-button flight)
#    info card, panels      selection details, setsize, script lines, filters, find
# ==============================================================================

# --- Vendored dependencies: dormant hook (this module is page text only) ---
import sys
import os
_LIBS_NAME = "libs" if sys.platform.startswith("win") else ("libs-mac" if sys.platform == "darwin" else "libs-linux")
_libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIBS_NAME)
if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
    sys.path.insert(0, _libs_dir)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<!--mohaa-map-viewer-rev:__REV__-->
<html lang="en"><head><meta charset="utf-8">
<!-- Built from untrusted game files and fully offline: every source is pinned to
     self/file/data/blob and outbound connections are blocked. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' data: blob: file:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ - MOHAA map viewer</title>
<script type="application/json" id="mohaa-map-info">__INFO__</script>
<style>
 :root{--bg:#0e1116;--panel:#161b22;--line:#2b333d;--txt:#d6dde6;--dim:#8b97a6;
       --tag:#f2f5f8;--origin:#c084fc;--sel:#7ee787;--hidden:#3a4654;--accent:#7ee787;
       --btn:#21272f;--onbg:#2d3a2d;--btnhover:#3d4754;--grid:#1b212a;--labelbg:8,11,16;
       --err:#f85149;--warn:#e3b341;--selcol:#ff4d4d;}
 :root.light{--bg:#f5f7fa;--panel:#ffffff;--line:#d0d7de;--txt:#1f2328;--dim:#57606a;
       --tag:#7c6408;--origin:#8250df;--sel:#0969da;--hidden:#c0c7cf;--accent:#0969da;
       --btn:#eef1f4;--onbg:#ddebff;--btnhover:#c2ccd6;--grid:#cdd5dd;--labelbg:255,255,255;
       --err:#cf222e;--warn:#9a6700;--selcol:#d1242f;}
 *{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--bg);
   color:var(--txt);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 #wrap{display:flex;height:100vh}
 #stage{flex:1;position:relative;min-width:0;overflow:hidden}
 /* WebGL draws the map; the 2D canvas on top draws labels, arrows and the crosshair. */
 #stage canvas{position:absolute;left:0;top:0;display:block;width:100%;height:100%}
 #gl{cursor:crosshair} #c{pointer-events:none}
 #side{width:328px;background:var(--panel);border-left:1px solid var(--line);
   display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden}
 .sect{padding:10px 12px;border-bottom:1px solid var(--line)}
 /* Embedded in the launcher: its top bar already has Theme / Shortcuts. */
 :root.embed #modelSect{display:none}
 .sect h2{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
 h1{margin:0;font-size:14px;color:var(--accent);word-break:break-all} .sub{color:var(--dim);font-size:11px}
 /* "N unreadable blocks skipped" under the map's stats: opens the list of them */
 a.errlink{color:var(--err);cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px}
 a.errlink:hover{text-decoration-style:solid}
 a.scrlink{color:var(--accent);cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px}
 a.scrlink:hover{text-decoration-style:solid}
 /* the real / simple / static-prop entity counts (each explains itself in its tooltip) */
 #stats .ek{cursor:help;border-bottom:1px dotted var(--line)} #stats .ek.over{color:var(--err)}
 .row{display:flex;align-items:center;gap:8px;margin:5px 0;flex-wrap:wrap}
 button,select{background:var(--btn);color:var(--txt);border:1px solid var(--line);
   border-radius:6px;padding:5px 9px;font:inherit;cursor:pointer;
   transition:background .12s,border-color .12s,box-shadow .12s,transform .05s}
 button:hover:not(:disabled),select:hover{border-color:var(--accent);box-shadow:0 1px 4px rgba(0,0,0,.28)}
 button:active:not(:disabled){transform:translateY(1px);background:var(--onbg)}
 button:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
 button:disabled{cursor:not-allowed;opacity:.45}
 button.on{background:var(--onbg);border-color:var(--accent);color:var(--accent)}
 button.sm{padding:2px 7px;font-size:11px;border-radius:4px}
 input[type=range]{flex:1;accent-color:var(--accent)}
 input[type=text],input[type=search]{background:var(--btn);color:var(--txt);border:1px solid var(--line);
   border-radius:4px;padding:4px 7px;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 input[type=text]:focus,input[type=search]:focus{outline:1px solid var(--accent);outline-offset:0}
 kbd{background:var(--btn);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:11px}
 .co{color:var(--dim);font-size:11px}
 .tg{display:flex;flex-wrap:wrap;gap:5px}
 .tg button{padding:3px 7px;font-size:11px}
 .tg button .k{color:var(--dim);font-size:10px;margin-left:4px}
 /* Entities with only some of its kinds hidden by their own buttons */
 .tg button.part{border-style:dashed}
 .tg button.on .k{color:inherit;opacity:.75}
 #hint{position:absolute;left:10px;bottom:8px;right:10px;color:var(--dim);font-size:11px;pointer-events:none;
   display:flex;gap:10px;flex-wrap:wrap}
 #hint span{background:rgba(var(--labelbg),.62);padding:2px 8px;border-radius:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
 #hint span.chip{pointer-events:auto;cursor:pointer}
 #hint span.chip:hover{color:var(--accent)}
 #sideTab{position:absolute;right:0;top:50%;transform:translateY(-50%);z-index:15;
   background:var(--panel);color:var(--dim);border:1px solid var(--line);border-right:none;
   border-radius:8px 0 0 8px;padding:14px 5px;cursor:pointer;font-size:12px;line-height:1;
   user-select:none;transition:color .12s,border-color .12s}
 #sideTab:hover{color:var(--accent);border-color:var(--accent)}
 #loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:30;
   background:var(--bg);color:var(--dim);font-size:12px;flex-direction:column;gap:10px}
 #loading .bar{width:260px;height:4px;background:var(--line);border-radius:2px;overflow:hidden}
 #loading .bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .15s}
 #loading .err{color:var(--err);max-width:520px;text-align:center;white-space:pre-wrap}
 .ov{position:absolute;inset:0;background:rgba(0,0,0,.45);display:flex;
   align-items:center;justify-content:center;z-index:20}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:16px 20px 14px;max-height:86%;max-width:92%;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.5)}
 .card h3{margin:0 0 10px;color:var(--accent);font-size:13px}
 /* The legend (L): one column per section (path nodes, entities, brushes), each scrolling
    on its own under its heading. A narrow window stacks them. */
 #legCard{width:1180px;height:min(640px,86%);display:flex;flex-direction:column;overflow:hidden}
 #legBody{flex:1 1 auto;min-height:0;display:flex}
 #legBody .sec{flex:1 1 0;min-width:0;overflow-y:auto;font-size:12px;padding:0 10px 0 14px;border-left:1px solid var(--line)}
 #legBody .sec:first-child{border-left:none;padding-left:0}
 #legBody h4{position:sticky;top:0;z-index:1;background:var(--panel);margin:0;padding:0 0 5px;
   font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}
 #legClose{flex:none;align-self:flex-start}
 /* Simulate's model picker */
 #simCard{width:560px;height:min(600px,86%);display:flex;flex-direction:column;overflow:hidden}
 #simQ{flex:none;width:100%;box-sizing:border-box}
 #simStat{flex:none;margin:6px 0 4px;min-height:14px}
 #simList{flex:1 1 auto;min-height:0;overflow-y:auto;border:1px solid var(--line);border-radius:6px;font-size:12px}
 #simList .sh{padding:6px 8px 2px;color:var(--dim);text-transform:uppercase;font-size:10px;letter-spacing:.1em}
 #simList .it{padding:3px 8px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 #simList .it:hover{background:var(--line)}
 #simList .it.on{color:var(--accent);font-weight:bold}
 .simMod{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 @media (max-width:820px){#legCard{height:auto}#legBody{flex-direction:column;overflow-y:auto}
   #legBody .sec{flex:none;overflow:visible;border-left:none;padding:0 0 12px}}
 #legBody .note{color:var(--dim);font-size:11px;margin:0 0 6px}
 #legBody .sub{color:var(--dim);text-transform:uppercase;font-size:10px;letter-spacing:.1em;padding:8px 0 2px}
 #legBody .lrow{display:flex;gap:9px;align-items:flex-start;padding:3px 0}
 #legBody .lrow .s{flex:none;padding-top:1px}
 #legBody .nm{font-weight:bold}
 #legBody .k{color:var(--dim);font-size:10px;margin-left:6px;border:1px solid var(--line);border-radius:3px;padding:0 4px}
 #legBody .ds{color:var(--dim);font-size:11px}
 .lsw{display:inline-block;width:24px;height:24px;border-radius:3px;border:1px solid rgba(0,0,0,.45);vertical-align:middle;
   object-fit:cover;box-sizing:border-box}
 .lsw.lnone{border:none;position:relative}
 .lsw .dia{position:absolute;left:4px;top:4px;width:16px;height:16px;transform:rotate(45deg);border:1px solid rgba(0,0,0,.45)}
 .lsw.ldark{background:#2b333d}
 .lsw.llab{background:rgba(var(--labelbg),.8);color:var(--accent);font-size:11px;line-height:22px;text-align:center}
 .lsw.lsel{background:linear-gradient(rgba(255,77,77,.5),rgba(255,77,77,.5)),#6b7480}
 .lsw.lhov{background:#6b7480;box-shadow:inset 0 0 0 3px #6b7480,inset 0 0 0 4px var(--accent)}
 /* The "more info" card sits on the right of the 3D view and stays open while you fly. */
 #info{position:absolute;right:14px;top:14px;bottom:44px;width:440px;max-width:calc(100% - 28px);z-index:18;
   display:none;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:10px;
   box-shadow:0 12px 40px rgba(0,0,0,.45)}
 #info.on{display:flex}
 /* MODIFY's Edit parameters, on the left of the 3D view */
 #modEd{position:absolute;left:14px;top:14px;width:380px;max-width:calc(100% - 28px);z-index:19;display:none;flex-direction:column;
   background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,.45)}
 #modEd.on{display:flex}
 #modEdHead{padding:10px 12px 8px;border-bottom:1px solid var(--line);cursor:move;user-select:none}
 #modEdHead .t{color:var(--accent);font-weight:bold}
 #modTxt{margin:8px 12px 4px;min-height:190px;resize:vertical;font:12px/1.4 Consolas,Menlo,monospace;background:var(--bg);color:var(--txt);
   border:1px solid var(--line);border-radius:6px;padding:6px 8px}
 #modErr{padding:0 12px 6px;color:var(--err);min-height:14px}
 #modList .li{height:22px;box-sizing:border-box;padding-top:0;padding-bottom:0}
 #modList .sw{width:10px;height:10px;border-radius:2px;flex:none;box-sizing:border-box}
 #modList .mtag{font-size:10px;padding:0 4px;border-radius:3px;border:1px solid var(--line);color:var(--dim);flex:none}
 #modList .mtag.nw{color:var(--accent);border-color:var(--accent)}
 #modList .mtag.ch{color:var(--warn);border-color:var(--warn)}
 #infoHead{display:flex;align-items:center;gap:8px;padding:10px 12px 8px;border-bottom:1px solid var(--line)}
 #infoHead .t{flex:1;min-width:0;color:var(--accent);font-weight:bold;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #infoBody{overflow:auto;padding:8px 12px 12px;flex:1;min-height:0}
 #infoBody h4{margin:12px 0 5px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);
   display:flex;align-items:center;gap:6px}
 #infoBody h4 .sp{flex:1}
 #infoBody table{border-collapse:collapse;width:100%;font-size:12px}
 #infoBody td{padding:2px 8px 2px 0;vertical-align:top;word-break:break-word}
 #infoBody td.k{color:var(--dim);white-space:nowrap;width:1%}
 #infoBody pre{margin:4px 0;padding:6px 8px;background:var(--bg);border:1px solid var(--line);border-radius:6px;
   white-space:pre-wrap;word-break:break-all;font-size:11.5px;max-height:240px;overflow:auto}
 #infoBody .note{color:var(--dim);font-size:11px;margin:3px 0}
 #infoBody .warn{color:var(--warn)}
 #infoBody a,.lnk{color:var(--accent);cursor:pointer;text-decoration:none}
 #infoBody a:hover,.lnk:hover{text-decoration:underline}
 #infoBody .desc{white-space:pre-wrap;color:var(--dim);font-size:11px;max-height:200px;overflow:auto}
 .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px;border:1px solid rgba(0,0,0,.35)}
 .face{padding:3px 0;border-top:1px dashed var(--line)}
 .face.hit{background:rgba(255,77,77,.12)}
 #selBox .row{margin:3px 0}
 #selSum{white-space:pre-wrap;word-break:break-word}
 .tabs{display:flex;gap:6px;margin-bottom:6px}
 .tabs button{flex:1;padding:4px 6px;font-size:11px}
 #listBox{max-height:none}
 /* the Find tabs' counts and hints, above the line that starts the list */
 #listHead .co{margin-top:4px}
 #listHead:empty{display:none}
 /* Shift+click a list row's coloured square: hide / show that entity or that class */
 .li .sw{cursor:pointer}
 .li{display:flex;align-items:center;gap:6px;padding:2px 5px;border-radius:4px;cursor:pointer;white-space:nowrap}
 .li:hover,.li.hot{background:var(--btn)}
 .li .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
 .li .ct{color:var(--dim);font-size:11px}
 .li .ar{color:var(--dim);font-size:10px;width:10px;text-align:center}
 .li img{width:18px;height:18px;object-fit:cover;border-radius:2px;flex:none;image-rendering:auto}
 .li.sub{padding-left:22px;font-size:12px}
 .li.sel .nm{color:var(--accent)}
 /* hidden (Hide, or a Show button off) in red; a class with some of its entities hidden in yellow */
 .li.hid .nm,.li.hid .ct{color:var(--err)} .li.part .nm,.li.part .ct{color:var(--warn)}
 /* the Entities tab's client slots (0 to sv_maxclients - 1): greyed, not clickable */
 .li.res{cursor:default;opacity:.45} .li.res:hover{background:none} .li.res .nm{color:var(--dim)}
 #findIn{width:100%}
 ::-webkit-scrollbar{width:10px;height:10px}
 ::-webkit-scrollbar-thumb{background:var(--line);border-radius:5px}
 ::-webkit-scrollbar-thumb:hover{background:var(--btnhover)}
 ::-webkit-scrollbar-track{background:transparent}
 /* the game cvars list (Display): the Model Viewer's pop-up list look */
 #cvarRow{margin-top:7px;flex-wrap:nowrap}
 #cvarBtn{display:flex;align-items:center;gap:6px;max-width:150px;flex:none;padding:3px 8px;font-size:11px}
 #cvarBtn .albl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
 #cvarBtn .acar{color:var(--dim);font-size:10px}
 #modClsBtn{display:flex;align-items:center;gap:6px;padding:3px 8px}
 #modClsBtn .albl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
 #modClsBtn .acar{color:var(--dim);font-size:10px}
 .amItem.hot{background:var(--btnhover)}
 .amItem.sel .lbl{color:var(--accent)}
 #cvarCount{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #cvarCount.on{color:var(--accent)}
 .amPanel{position:fixed;z-index:71;display:flex;flex-direction:column;background:var(--panel);
   border:1px solid var(--line);border-radius:6px;box-shadow:0 8px 26px rgba(0,0,0,.45);
   width:340px;max-height:78vh;padding:4px 0}
 .amHead{display:flex;align-items:center;gap:6px;padding:3px 8px 5px 8px;color:var(--dim);
   font-size:11px;border-bottom:1px solid var(--line);margin-bottom:4px}
 .amHead .amPathTxt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .amHead .amReset{padding:1px 8px;font-size:11px}
 .amSearch{width:calc(100% - 12px);margin:2px 6px 5px 6px;padding:3px 6px;
   background:var(--btn);color:var(--txt);border:1px solid var(--line);border-radius:4px;
   font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 .amSearch:focus{outline:1px solid var(--accent);outline-offset:0}
 .amBody{overflow-y:auto;overflow-x:hidden;min-height:0}
 .amItem{display:flex;align-items:center;gap:6px;padding:3px 8px;cursor:pointer;white-space:nowrap;overflow:hidden}
 .amItem:hover{background:var(--btnhover)}
 .amItem .arw{flex:none;width:12px;text-align:center;color:var(--accent);font-size:11px}
 .amItem .lbl{flex:none;min-width:0;overflow:hidden;text-overflow:ellipsis}
 .amItem .cnt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--dim);font-size:11px;text-align:right}
 .amItem.on .lbl{color:var(--accent)}
 .amItem.na .lbl,.amItem.na .arw{opacity:.5}
 .amItem input{flex:none;width:70px;padding:1px 4px;background:var(--btn);color:var(--txt);border:1px solid var(--line);
   border-radius:4px;font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 .amItem input:focus{outline:1px solid var(--accent);outline-offset:0}
 .amItem input.wide{width:92px}
 .amGrp{padding:6px 8px 2px 8px;color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.06em;
   border-top:1px solid var(--line);margin-top:3px;cursor:default}
 .amGrp:first-child{border-top:0;margin-top:0;padding-top:2px}
 .amNote{padding:4px 8px;color:var(--dim);font-size:11px;white-space:normal}
 #cvWhere{border-top:1px solid var(--line);margin-top:4px;padding-top:5px}
 #cvWhere div{margin:1px 0} #cvWhere .msg{color:var(--accent)} #cvWhere .warn{color:var(--warn)}
 /* the hotkey on the All / In-game look / Editor look buttons */
 .row button .k{color:var(--dim);font-size:10px;margin-left:4px} .row button.on .k{color:inherit;opacity:.75}
__KEYS_CSS__
</style>
<script>
/* Boot flags from the URL hash the launcher opens us with (#embed&theme=dark), applied
   before first paint. Without a hash (plain browser) the page uses its own layout. */
(function(){try{
  var raw=(location.hash||"").replace(/^#/,""),p={};
  raw.split("&").forEach(function(kv){if(!kv)return;var i=kv.indexOf("=");
    if(i<0)p[decodeURIComponent(kv)]=true;
    else p[decodeURIComponent(kv.slice(0,i))]=decodeURIComponent(kv.slice(i+1));});
  window.__HOSTEMBED__=!!p.embed;
  var t=(""+(p.theme||"")).toLowerCase();
  window.__HOSTTHEME__=(t==="light"||t==="dark")?t:"";
  var el=document.documentElement;
  if(window.__HOSTEMBED__)el.classList.add("embed");
  if(window.__HOSTTHEME__)el.classList.toggle("light",window.__HOSTTHEME__==="light");
}catch(_e){}})();
</script></head>
<body><div id="wrap">
 <div id="stage"><canvas id="gl"></canvas><canvas id="c"></canvas>
  <div id="hint"><span class="chip" id="hintHelp" title="Keyboard shortcuts (H)"><kbd>H</kbd> hotkeys</span><span class="chip" id="hintLeg" title="What the colours, markers and editor surfaces mean (L)"><kbd>L</kbd> legend</span><span id="hintCam"></span><span id="hintHover"></span></div>
  <div id="sideTab" title="Collapse the control panel (\)">&#10095;</div>
  <div id="info"><div id="infoHead"><span class="t" id="infoTitle">info</span>
    <button class="sm" id="infoCopy" title="Copy everything in this card as text">Copy</button>
    <button class="sm" id="infoScr" style="display:none" title="Open the map's .scr in your Text Editor (from the launcher; in a browser its path is copied)">Open .scr</button>
    <button class="sm" id="infoClose" title="Close (Esc)">&#10005;</button></div>
    <div id="infoBody"></div></div>
  <div id="modEd"><div id="modEdHead"><span class="t" id="modEdT">Edit parameters</span></div>
    <textarea id="modTxt" spellcheck="false"></textarea>
    <div id="modErr" class="co"></div>
    <div class="row" style="gap:5px;padding:0 12px 10px;align-items:center"><span class="co" style="flex:1">"key" "value" per line</span>
      <button class="sm" id="bModUndo" title="Undo the last change made since this box opened (Ctrl+Z)">Undo</button><button class="sm" id="bModRedo" title="Redo what Undo took back (Ctrl+Y or Ctrl+Shift+Z)">Redo</button>
      <button class="sm" id="bModDone" title="Keep it and place it again (Esc)">Done</button></div></div>
  <div id="loading"><div id="loadMsg">Loading map&hellip;</div><div class="bar"><i id="loadBar"></i></div></div>
  <!-- keyboard shortcuts (H): the keyboard map, built from MAP_VIEWER_KEYS on first open -->
  <div id="helpOv" class="kx-ov" style="display:none"><div class="kx-card" id="helpCard"></div></div>
  <div id="simOv" class="ov" style="display:none">
   <div class="card" id="simCard">
    <h3>Simulate with a model</h3>
    <input id="simQ" type="text" spellcheck="false" autocomplete="off" placeholder="Search models, e.g. vehicles/stuka">
    <div id="simStat" class="co"></div>
    <div id="simList"></div>
    <div class="row" style="margin-top:10px">
      <button id="simBoxBtn" title="Fly a plain box with a nose instead of a model">Placeholder box</button>
      <span style="flex:1"></span>
      <button id="simClose" title="Close (Esc)">Close</button></div>
   </div>
  </div>
  <div id="legOv" class="ov" style="display:none">
   <div class="card" id="legCard">
    <h3>Legend</h3>
    <div id="legBody"></div>
    <button id="legClose" style="margin-top:10px" title="Close the legend (Esc or L)">Close</button>
   </div>
  </div>
 </div>
 <div id="side">
   <div class="sect"><h1 id="ttl">map</h1><div class="sub" id="stats"></div><div class="sub" id="msgLine"></div></div>
   <div class="sect" id="modelSect">
     <h2>Map</h2>
     <div class="row">
       <button id="bTheme" style="flex:1" title="Toggle Light / Dark theme (T). Your choice is remembered.">&#9728; Light mode</button>
       <button id="bHelp" title="Show the viewer's keyboard shortcuts (H)">? Shortcuts</button>
       <button id="bLegend" title="What the colours, markers and editor surfaces mean (L)">Legend</button>
     </div>
   </div>
   <div class="sect" id="selSect">
     <h2>Selection</h2>
     <div id="selSum" class="co">Click anything in the map to select it.</div>
     <div class="row" id="selBtns" style="display:none">
       <button class="sm" id="bInfo" title="Everything about the selection: keys, origin, setsize, targets, textures (N, or Ctrl+click)">&#9432; More info</button>
       <button class="sm" id="bFocus" title="Fly the camera to the selection (F, or double-click)">Fly to</button>
       <button class="sm" id="bHide" title="Hide the selection (Backspace). Shift+H shows everything again.">Hide</button>
       <button class="sm" id="bClear" title="Clear the selection (Esc)">Clear</button>
       <button class="sm" id="bEye" style="display:none" title="Eye view: put the camera where the entity sees from, facing its angles or its target">Eye view</button>
       <button class="sm" id="bSameSf" disabled title="Select every entity of the same class with the same spawnflags (the selected entity has none)">Same spawnflags</button>
       <button class="sm" id="bSameErr" disabled title="Select every path node with the same error as the selected path node(s): none of the selected path nodes has an error">Same error</button>
       <button class="sm" id="bSame" title="Select everything of the same kind: same class for entities, same texture for brushes (Alt+click)">Same kind</button>
       <button class="sm" id="bPath" style="display:none" title="Select the whole path through this entity: everything its &quot;target&quot; leads to and everything that leads to it (Ctrl+Alt+click)">Same path</button>
       <button class="sm" id="bTname" style="display:none" title="Select every entity with this targetname ($, that is Shift+4)">Same targetname</button>
       <button class="sm" id="bDoor" style="display:none" title="Open or close the selected door as in game (O)">Open door</button>
       <button class="sm" id="bExpRun" style="display:none">Run exploder</button>
       <button class="sm" id="bExpReset" style="display:none">Reset exploder</button>
       <button class="sm" id="bLightOff" style="display:none" title="Turn the selected lights off, as if they had never been there: the light they gave the map (its lightmaps, vertex light, props and models) goes, the rest stays. Display's Lights off turns every light off">Turn off</button>
       <button class="sm" id="bLightOn" style="display:none" title="Turn the selected lights back on">Turn on</button>
     </div>
     <div class="row co" id="hidLine" style="display:none"><span id="hidCount"></span><button class="sm" id="bUndoHide" title="Undo the last Hide or Show all (Ctrl+Z); press again for the one before">Undo</button><button class="sm" id="bUnhide" title="Show everything you hid (Shift+H); Ctrl+Z hides it again">Show all</button></div>
   </div>
   <div class="sect" id="simSect" style="display:none">
     <h2>Simulate</h2>
     <div id="simSpl">
     <div class="row">
       <button class="sm" id="bSim" title="Fly a model along this info_splinepath's path from its first node, as a script's followpath does">&#9654; Simulate</button>
       <button class="sm" id="bSimReset" disabled title="Stop the simulation and take the model away">Reset</button>
     </div>
     <div id="simSum" class="co" style="white-space:pre-line"></div>
     <div class="row" style="align-items:center">
       <span class="co">Model</span><span id="simModel" class="simMod"></span>
       <button class="sm" id="bSimPick" title="Choose the model that flies the path: any model in the paks (from the launcher), or a model this map places">Choose&hellip;</button>
     </div>
     <div class="row" style="align-items:center">
       <span class="co">Speed</span>
       <select id="simMul" title="How fast the simulation plays: 1x is the game's own speed">
         <option value="0.25">0.25x</option><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option><option value="4">4x</option></select>
       <label class="co" title="Follow: keep the camera behind the model while it flies, looking at it (with Eye view too: from behind it at its own angles, turning and banking with it). Moving the camera by hand stops it"><input type="checkbox" id="simCam"> Follow</label>
       <label class="co" title="Eye view: the camera starts on the path's first node, facing the node's angles, and stays there (with Follow too: rides with the model at its own angles)"><input type="checkbox" id="simEye"> Eye view</label>
     </div>
     <div class="row co" id="simTime"></div>
     <div class="row co" title="How far behind the model the camera follows (the mouse wheel changes it while the camera follows)">camera zoom <input type="range" id="simZoom" min="0" max="100" step="1" value="40"><span id="simZoomV" style="min-width:34px;text-align:right"></span></div>
     </div>
     <div id="simNd" style="display:none">
       <div class="row" style="align-items:center">
         <span class="co">Human</span>
         <select id="actHum" style="flex:1;min-width:0" disabled title="The human who stands on the node: any actor model in the paks (models/human). The launcher builds the one you choose, and only that one"></select>
       </div>
       <div class="row" style="align-items:center">
         <span class="co">Weapon</span>
         <select id="actWpn" style="flex:1;min-width:0" disabled title="The weapon in his hand: any weapon model in the paks (no grenades). Its weapon group (in brackets) names the animations he plays"></select>
       </div>
       <div class="row">
         <button class="sm" id="bActSpawn" disabled title="Stand the chosen human on this path node, dropped to the floor and facing the node's angle, idling">Spawn</button>
         <button class="sm" id="bActPause" disabled title="Freeze him exactly where he is, mid-animation; press again to carry on">Pause</button>
         <button class="sm" id="bActFly" disabled title="Fly the camera to him, wherever he is now">Fly to</button>
         <button class="sm" id="bActFollow" disabled title="The game's third-person camera behind his head (cg_cameradist 120, cg_cameraheight 18): it moves in to keep out of walls, and tips up over him when it is against one. Moving the camera by hand turns it off">Follow</button>
       </div>
       <div class="row" style="gap:4px;flex-wrap:wrap">
         <button class="sm" id="bActSim" disabled title="Play the animation the game plays at a node with these spawnflags (CORNER_LEFT, CORNER_RIGHT, CRATE, SNIPER, DUCK), to check that it isn't blocked by a wall or crate">&#9654; Simulate</button>
         <span id="actMoveWrap" style="position:relative;display:inline-block">
           <button class="sm" id="bActMove" disabled title="Run or walk along the target chain, or to a spot you pick">&#10140; Move &#9662;</button>
           <div id="actMoveMenu" style="display:none;position:absolute;left:0;top:100%;margin-top:2px;z-index:20;flex-direction:column;gap:2px;padding:3px;background:#1b1f27;border:1px solid #3a4150;border-radius:4px;min-width:100%">
             <button class="sm" id="bActRunPath" disabled style="white-space:nowrap;text-align:left" title="Run along this node's &quot;target&quot; chain: to its target, then that one's target, and so on (greyed out when it has no target)">&#9654; Run path</button>
             <button class="sm" id="bActRunTo" disabled style="white-space:nowrap;text-align:left" title="Run to a node, an entity or a spot you click next (Esc cancels). A path node or any other spot is reached over the AI's path nodes; an info_waypoint is walked to in a straight line">&#9654; Run to</button>
             <button class="sm" id="bActWalkPath" disabled style="white-space:nowrap;text-align:left" title="Walk along this node's &quot;target&quot; chain instead of running (greyed out when it has no target)">&#9654; Walk path</button>
             <button class="sm" id="bActWalkTo" disabled style="white-space:nowrap;text-align:left" title="Walk to a node, an entity or a spot you click next (Esc cancels)">&#9654; Walk to</button>
           </div>
         </span>
         <button class="sm" id="bActTrace" title="Draw the path he is following: the whole way in blue, the part still to go in red. Off by default; turns on with AI routes, and can be turned off after">Trace path</button>
       </div>
       <div id="actSum" class="co" style="white-space:pre-line"></div>
     </div>
   </div>
   <div class="sect">
     <h2>Camera</h2>
     <div class="row">
       <button id="bFree" class="on" style="flex:1" title="Fly camera: mouse drag looks around, WASD moves, Space/C rise/lower (V switches)">Free-look</button>
       <button id="bRad" style="flex:1" title="MOHRadiant's camera: hold the right mouse button and push the mouse to fly; arrows, comma/period, D/C and A/Z as in the editor; Shift goes faster (V switches)">Radiant-look</button>
     </div>
     <div id="camHelpFree">
       <div class="row co">mouse drag = look</div>
       <div class="row co">mouse wheel = move</div>
       <div class="row co"><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> move</div>
       <div class="row co"><kbd>Q</kbd>/<kbd>E</kbd> tilt</div>
       <div class="row co"><kbd>Space</kbd>/<kbd>C</kbd> up/down</div>
       <div class="row co"><kbd>Shift</kbd> fast camera</div>
       <div class="row co"><kbd>U</kbd> level camera</div>
       <div class="row co"><kbd>X</kbd> stop camera</div>
     </div>
     <div id="camHelpRad" style="display:none">
       <div class="row co">right-drag = fly (push up to go forward)</div>
       <div class="row co"><kbd>&uarr;</kbd><kbd>&darr;</kbd> move</div>
       <div class="row co"><kbd>&larr;</kbd><kbd>&rarr;</kbd> turn</div>
       <div class="row co"><kbd>,</kbd><kbd>.</kbd> strafe</div>
       <div class="row co"><kbd>D</kbd>/<kbd>C</kbd> up/down</div>
       <div class="row co"><kbd>A</kbd>/<kbd>Z</kbd> look</div>
       <div class="row co"><kbd>U</kbd> level camera</div>
       <div class="row co"><kbd>Shift</kbd> fast camera</div>
       <div class="row co"><kbd>Ctrl</kbd> grid step</div>
       <div class="row co"><kbd>X</kbd> stop camera</div>
     </div>
     <div class="row co">speed <input type="range" id="speed" min="50" max="3000" step="50" value="500" title="Camera speed in units per second (hold Shift for 4x)"><span id="speedV" style="min-width:34px;text-align:right">500</span></div>
     <div class="row co">fov <input type="range" id="fov" min="60" max="150" step="1" value="90" title="Horizontal field of view in degrees (the game's default is 80)"><span id="fovV" style="min-width:34px;text-align:right">90</span></div>
     <div class="row co"><button class="sm" id="bClip" title="Cubic clipping: hide everything further than the distance on the right, as MOHRadiant does (Ctrl+\). [ and ] change the distance.">Cubic clip</button><input type="range" id="clipD" min="256" max="16384" step="128" value="4096" style="max-width:110px"><span id="clipV">4096</span></div>
     <div class="row co" style="gap:5px">
       <input type="text" id="gotoIn" placeholder="go to: x y z" style="flex:1;min-width:0" title="Type or paste a position, e.g. ( 512 -128 64 ), and press Enter">
       <button class="sm" id="bCopyCam" title="Copy the camera position as ( x y z ) for a script">Copy pos</button>
     </div>
     <div class="row co" style="gap:5px">
       <input type="text" id="angIn" placeholder="angles: pitch yaw roll" style="flex:1;min-width:0" title="Type or paste angles, e.g. ( 15 90 0 ), and press Enter to turn the camera to them, as the game takes angles: pitch (looking down is positive), yaw, roll">
       <button class="sm" id="bCopyAng" title="Copy the camera's angles as ( pitch yaw roll ) for a script, as the game takes them (looking down is a positive pitch)">Copy ang</button>
     </div>
   </div>
   <div class="sect">
     <h2>Display</h2>
     <div class="tg" id="dispBtns"></div>
     <div class="row co" style="align-items:center;margin-top:8px">backdrop
       <input type="color" id="bgcol" value="#0e1116" style="width:44px;height:22px;padding:1px;border:1px solid var(--line);border-radius:6px;background:var(--btn);cursor:pointer" title="Backdrop colour behind the map. Overrides the theme's default; remembered.">
       grid
       <input type="color" id="gridcol" value="#6fd6e8" style="width:44px;height:22px;padding:1px;border:1px solid var(--line);border-radius:6px;background:var(--btn);cursor:pointer" title="Colour of the grid's lines and numbers (Grid, +). Remembered.">
       <button class="sm" id="bgReset" title="Return the backdrop and the grid to the theme's default colours">Default</button>
     </div>
     <div class="row co" style="align-items:center"><button class="sm" id="bGrid" style="min-width:66px" title="Which planes the grid draws: Grid XY (flat, like the floor), Grid XZ and Grid YZ (upright), or Grid all (the whole 3D lattice). Click for the next. The grid itself turns on and off with Grid in the buttons above (+)">Grid XY</button><input type="range" id="gridSz" min="0" max="9" step="1" value="3" style="flex:1;min-width:0" title="Grid size: MOHRadiant's 1, 2, 4, 8, 16, 32, 64, 128, 256 or 512 units ({ and })"><span id="gridV" style="min-width:34px;text-align:right">8</span></div>
     <div class="row co" id="cvarRow"><button id="cvarBtn" title="The game's debugging cvars, doing here what they do in game: what the renderer draws from where the camera is (r_showtris, r_shownormals, r_lockpvs, r_showsky, r_farplane...), its lightmaps and light grid (r_lightmap, r_light_showgrid), entity numbers, boxes and info (sv_showentnums, sv_showbboxes, g_entinfo), cameras, rain and the AI's path nodes. Type a cvar and a value in its box as in the game's console. (` like the game's console key)"><span class="albl">&mdash; game cvars &mdash;</span><span class="acar">&#9668;</span></button><span id="cvarCount">none set</span></div>
   </div>
   <div class="sect">
     <h2>Show</h2>
     <div class="tg" style="margin-bottom:7px"><button id="bFull" title="Full Brightness (B). Off: the map lit the way the game lights it (lightmaps, vertex light). On: every texture at full brightness, as MOHRadiant shows it.">Full Brightness<span class="k">B</span></button><button id="bSimpleSky" title="Simple Sky (K). On: the sky brushes solid, their picture tiled, as MOHRadiant draws them. Off: the game's sky box and its moving clouds, drawn behind everything, so whatever is behind a sky brush shows through it as in game.">Simple Sky<span class="k">K</span></button><button id="bSimpleMod" title="Simple models (M). On: each tree that has a sprite version is drawn as that sprite alone, the way the game draws trees far away; it turns about its upright axis to face the camera. Off: the whole tree. Models with no sprite version (bushes, props) don't change.">Simple models<span class="k">M</span></button><button id="bRoutes" title="AI routes: the game cvar ai_showroutes (game cvars, `): the connections the AI can walk between path nodes, from the map's .pth file (worked out here when it has none, and for Modify's new nodes), green both ways, a red arrowhead one way. Only the nodes within ai_showroutes_distance of the camera (I)">AI routes<span class="k">I</span></button><button id="bAiErr" title="AI errors: the tags over path nodes saying what is wrong with them: no paths, N one-way, own group of N (joined to each other but not to the map's other nodes), in the wall, no angle (a CORNER_LEFT, CORNER_RIGHT, CRATE or LOW_WALL_ARC node without an angle). On by itself when AI routes is turned on and off when it is turned off; click to hide or show them while AI routes stays on. Tags that aren't errors (DONT_LINK, a duplicate, 48 paths or a cell full) stay">AI errors</button><button id="bSunFlare" title="Sun flare (J). On: the game's lens flare, drawn as the game draws it when the view looks toward the map's sun and nothing solid is between the camera and the sky that way, with the screen's glare that fades when the sun goes out of sight. Off: no flare, as in MOHRadiant.">Sun flare<span class="k">J</span></button></div>
     <div class="tg" id="filtBtns" style="margin-bottom:7px"></div>
     <button id="bShowAll" title="Show every group (Ctrl+A)">All<span class="k">Ctrl+A</span></button>
     <!-- the two looks, as wide as the panel like the cameras' buttons; each is on while the
          Show buttons, the light, the sky and the sun flare are as it sets them (the flare
          only on a map that has one). A name never breaks: in a
          panel too narrow for it, the key goes under the name, both buttons as tall -->
     <div class="row" style="align-items:stretch">
       <button id="bGameView" style="flex:1" title="Hide what the game never draws (caulk, clips, triggers, hints, origin brushes, areaportals) and the entity markers, with the game's lighting, sky and sun flare: Full Brightness and Simple Sky off, Sun flare on (G)">In-game&nbsp;look<wbr><span class="k">G</span></button>
       <button id="bEditView" style="flex:1" title="MOHRadiant's view: everything except hints, areaportals and rain, at full brightness with Simple Sky on and Sun flare off (Shift+G)">Editor&nbsp;look<wbr><span class="k">Shift+G</span></button>
     </div>
   </div>
   <div class="sect" id="modSect">
     <h2>Modify</h2>
     <div class="row" style="gap:5px">
       <button id="modClsBtn" style="flex:1;min-width:0" title="The class of the entity to add. Type to search every class - the entity definitions' and the map's - then click a row or press Enter to take the top match."><span class="albl">info_pathnode</span><span class="acar">&#9668;</span></button>
       <button class="sm" id="bModAdd" title="Add an entity of this class: then click anywhere on the map to place it there (a path node goes 16 units over the spot; the game drops it to the floor). Esc or Add again cancels. It stays see-through, and out of the map's own lists, until saved&#10;&#10;Hotkey: Alt+A">Add</button>
     </div>
     <div class="row" style="gap:4px;flex-wrap:wrap;margin-top:6px">
       <button class="sm" id="bModEdit" title="Edit the entity as the .bsp's entity lump holds it: &quot;key&quot; &quot;value&quot; lines, applied as you type. A path node joins the AI's paths again when you're done&#10;&#10;Hotkey: Alt+E">Edit parameters</button>
       <button class="sm" id="bModMove" title="Move: the selected entity follows the mouse again; a click on the map puts it there (Esc or Move again cancels). Off while Trim origin is on&#10;&#10;Hotkey: Alt+M">Move</button>
       <button class="sm" id="bModTrim" title="Trim origin: the camera stops and W A S D / the arrow keys move the entity along the map's axes (the way you face), Space / C up and down, by the trim step. Esc or T stops&#10;&#10;Hotkey: Alt+T">Trim origin</button>
       <button class="sm" id="bModYaw" title="Yaw: turn the selected entity to the next of 0, 90, 180 and 270 degrees (one that faces none of those starts at 0). An info_ class gets &quot;angle&quot;, anything else &quot;angles&quot; &quot;0 yaw 0&quot;. Every selected row turns to the same yaw; each press is one Undo step&#10;&#10;Hotkey: Alt+R">Yaw</button>
       <button class="sm" id="bModLink" title="Make path: click another entity to set this one's &quot;target&quot; to its targetname (only entities that have one can be picked), drawn as a target link. The clicked one is selected after, so pressing Make path again goes on along the path (info_waypoint, info_splinepath, script_origin...). Esc cancels">Make path</button>
       <button class="sm" id="bModEye" title="Eye view: put the camera where the entity sees from, as Eye view does for the map's entities: a path node, a player start or an AI 82 units above the floor under it, anything else at its origin, facing its angles, else its target, else yaw 0">Eye view</button>
       <button class="sm" id="bModFly" title="Fly the camera to the entity&#10;&#10;Hotkey: click its row in the list again once it is selected (green), or double-click the row">Fly to</button>
       <button class="sm" id="bModSf" title="Spawnflags: tick the selected entity's spawnflags from the list of its class (a path node: DONT_LINK, DUCK, COVER, CONCEALMENT, CORNER_LEFT, CORNER_RIGHT, SNIPER, CRATE, and LOW_WALL_ARC for Spearhead / Breakthrough only)&#10;&#10;Hotkey: Alt+S">Spawnflags</button>
       <button class="sm" id="bModDup" title="Copy: the selected entities again (Shift+click adds more to the selection, the map's own entities selected in the view too), without targetname or target. They follow the mouse together, spaced as they are, until a click puts them down; Esc takes them away&#10;&#10;Hotkey: Alt+C">Copy</button>
       <button class="sm" id="bModHUndo" title="Undo the last change to Modify's entities, back to none added&#10;&#10;Hotkey: Alt+Z">Undo</button>
       <button class="sm" id="bModHRedo" title="Redo the last change undone&#10;&#10;Hotkey: Alt+Y or Alt+Shift+Z">Redo</button>
       <button class="sm" id="bModDel" title="Remove the entity&#10;&#10;Hotkey: Delete">Delete</button>
     </div>
     <div class="co" id="modScr" style="display:none;margin-top:6px;color:var(--warn)"></div>
     <div class="row co" style="margin-top:6px">trim step <input type="range" id="modStep" min="0" max="13" step="1" value="4" title="How far one key press of Trim origin moves it, 1 to 50 units"><span id="modStepV" style="min-width:22px;text-align:right">5</span></div>
     <div class="row" style="gap:4px;flex-wrap:wrap">
       <button class="sm" id="bModSaveBsp" title="Save a copy of the .bsp with the new entities in its entity lump (everything else byte for byte) and a new &quot;map_time&quot;, so the game rebuilds the AI's .pth. Never over the original">Save as .bsp</button>
       <button class="sm" id="bModSaveMap" title="Save the .map with the new entities added, as a new file">Save as .map</button>
       <button class="sm" id="bModCopy" title="Copy the new entities as entity-lump text">Copy text</button>
     </div>
     <div class="co" id="modStat" style="margin-top:4px"></div>
     <!-- the entities, newest first, under the buttons so Add stays beside them however long it gets -->
     <div id="modList" style="margin-top:6px"></div>
   </div>
   <div class="sect">
     <h2>Find</h2>
     <input type="search" id="findIn" placeholder="class, targetname, key, value, texture..." title="Type to search every entity's keys and values and every texture name. Enter selects all matches; click a result to select it and fly there. (Ctrl+F or /)&#10;&#10;&quot;exact value&quot; · $targetname · key: value (classname:, targetname:, texture:, #set:, entity:, entnum:; * for any letters; key: alone for any value) · entity 25 · ( x y z ) for an origin · -term leaves out what it matches">
     <div class="tabs" style="margin-top:7px">
       <button id="tabFind" class="on" title="Search results">Results</button>
       <button id="tabCls" title="Every entity class in the map, like MOHRadiant's Map Info and Entities windows">Classes</button>
       <button id="tabTex" title="Every texture the map uses">Textures</button>
       <button id="tabEnt" title="Every entity the game gives an entity number to (what sv_showentnums shows), in that order, for the game the cvars set (g_gametype, skill, developer, sv_maxclients)">Entities</button>
     </div>
     <div id="listHead"></div>
   </div>
   <!-- the list itself, under a line of its own (empty: hidden) -->
   <div class="sect" id="listSect"><div id="listBox"></div></div>
 </div>
</div>
<script id="mapdata" type="application/octet-stream">__DATA__</script>
<script type="application/json" id="mohaa-keys">__KEYS__</script>
<script>
__KEYS_JS__
</script>
<script>
'use strict';
/*CORE-BEGIN*/
// ============================================================================
//  .map reader and geometry builder (no page or WebGL code in here)
// ============================================================================
// A .map file is a list of entities. Each entity has "key" "value" pairs and any
// number of primitives: brushes (a list of planes, each given by three points and
// a texture), patchDef2/3 curved patches (a grid of Bezier control points) and
// terrainDef blocks (MOHAA's LOD terrain: a heightmap on a 64-unit grid).
// readMap() turns the text into that structure, keeping each piece's position in
// the text so the viewer can show and copy its source.

// Content and surface bits that matter here (qcommon/surfaceflags.h)
const CONTENTS_DETAIL=0x8000000, CONTENTS_ORIGIN=0x1000000, CONTENTS_TRANSLUCENT=0x20000000,
      CONTENTS_TRIGGER=0x40000000, CONTENTS_AREAPORTAL=0x8000, CONTENTS_FOG=0x40,
      CONTENTS_LIQUID=0x8|0x10|0x20, CONTENTS_CLIPS=0x10000|0x20000|0x40000|0x80000;
// Texture render hints from the build (keep in step with TF_* in mohaa_map_view.py)
const TF_SKY=1, TF_NODRAW=2, TF_ALPHATEST=4, TF_BLEND=8, TF_ADD=16, TF_TWOSIDED=32, TF_MISSING=64, TF_SPRITE=128, TF_FILTER=256,
      TF_LOD=512;
// What a face or marker is, for the Show filters (one bit per filter group)
const C_WORLD=1<<0, C_DETAIL=1<<1, C_ENTBRUSH=1<<2, C_PATCH=1<<3, C_TERRAIN=1<<4, C_CAULK=1<<5,
      C_CLIP=1<<6, C_TRIGGER=1<<7, C_HINT=1<<8, C_SKY=1<<9, C_LIQUID=1<<10, C_TRANS=1<<11,
      C_ORIGIN=1<<12, C_PORTAL=1<<13, C_NODRAW=1<<14, C_POINT=1<<15, C_LIGHT=1<<16, C_AINODE=1<<17,
      C_PATH=1<<18, C_MODEL=1<<19, C_STATIC=1<<20, C_VIS=1<<21, C_RAIN=1<<22, C_FOLIAGE=1<<23, C_SCRIPT=1<<24, C_SCRTRIG=1<<25;
const C_ENTITIES=C_ENTBRUSH|C_POINT|C_LIGHT|C_AINODE|C_PATH|C_MODEL|C_STATIC|C_VIS;
// C_STATIC has no Show button of its own: it marks the static props, which get no label
// unless selected; Models and Entities hide them. C_RAIN (common/rain, the volumes of
// func_rain entities) and C_FOLIAGE (common/foliageclip) have their own Show buttons,
// apart from Nodraw and Clips. C_SCRTRIG is no entity's kind: it shows or hides the
// volumes of the triggers the level script spawns (drawScriptTrigs). C_SCRIPT marks the
// entities the level script spawns
// (scriptEnts), on top of their own kind.

// ---- tokenizer -------------------------------------------------------------
// Tokens: { } ( ) "quoted text" and bare words. // starts a comment that runs to
// the end of the line. Each token keeps its start and end offset in the text.
function mapTokens(text){
  const toks=[], st=[], en=[];
  const n=text.length; let i=0;
  while(i<n){
    const c=text.charCodeAt(i);
    if(c<=32){i++;continue;}
    if(c===47&&text.charCodeAt(i+1)===47){            // //comment
      const e=text.indexOf('\n',i); i=(e<0)?n:e+1; continue;}
    if(c===123||c===125||c===40||c===41){toks.push(text[i]);st.push(i);en.push(i+1);i++;continue;}
    if(c===34){                                          // "quoted"
      const e=text.indexOf('"',i+1); const j=(e<0)?n:e;
      toks.push({q:text.slice(i+1,j)}); st.push(i); en.push(Math.min(n,j+1)); i=j+1; continue;}
    let j=i+1;
    while(j<n){const d=text.charCodeAt(j); if(d<=32||d===123||d===125||d===40||d===41||d===34)break; j++;}
    toks.push(text.slice(i,j)); st.push(i); en.push(j); i=j;
  }
  return {t:toks,s:st,e:en};
}
function tokStr(t){return (typeof t==='string')?t:t.q;}

// ---- parser -------------------------------------------------------------------
function readMap(text){
  const T=mapTokens(text), t=T.t, N=t.length;
  let p=0;
  const ents=[], errors=[];
  const num=()=>{const v=parseFloat(tokStr(t[p++])); return isFinite(v)?v:0;};
  const isNum=k=>{if(k>=N)return false;const s=t[k];return typeof s==='string'&&/^[-+]?(\d|\.\d)/.test(s);};
  // An error keeps where in the text it happened (off), for the list of skipped blocks.
  const fail=msg=>{const err=new Error(msg);err.off=(p<N)?T.s[p]:text.length;throw err;};
  const expect=ch=>{if(t[p]!==ch)fail('expected "'+ch+'" but found '+(p<N?'"'+tokStr(t[p]).slice(0,24)+'"':'the end of the file'));p++;};
  // A texture name is one word, as q3map and Radiant read it (GetToken stops only at white
  // space), even one that starts with a bracket: a brush in Spearhead's t1l1 has the
  // shader "textures/(0", which the tokenizer splits into "(" and "0".
  const word=()=>{
    if(p>=N)return '';
    if(typeof t[p]!=='string')return tokStr(t[p++]);
    const s=T.s[p];let e=s;while(e<text.length&&text.charCodeAt(e)>32)e++;
    while(p<N&&T.s[p]<e)p++;
    return text.slice(s,e);};
  const skipBlock=()=>{let d=0;do{if(t[p]==='{')d++;else if(t[p]==='}')d--;p++;}while(p<N&&d>0);};
  function vec3(){expect('(');const v=[num(),num(),num()];expect(')');return v;}
  function face(){
    const a=vec3(),b=vec3(),c=vec3();
    const f={p:[a[0],a[1],a[2],b[0],b[1],b[2],c[0],c[1],c[2]],tex:'',sh:[0,0],rot:0,sc:[0.5,0.5],cont:0,flags:0,val:0,extra:'',tm:null};
    if(t[p]==='('&&t[p+1]==='('){                    // brush primitives: ( ( a b c ) ( d e f ) )
      expect('(');expect('(');const r0=[num(),num(),num()];expect(')');expect('(');const r1=[num(),num(),num()];expect(')');expect(')');
      f.tm=[r0,r1];
    }
    f.tex=word();
    const nums=[];
    if(!f.tm){while(nums.length<5&&isNum(p))nums.push(num());
      if(nums.length>=5){f.sh=[nums[0],nums[1]];f.rot=nums[2];f.sc=[nums[3]||0.5,nums[4]||0.5];}}
    const tail=[];
    while(p<N&&t[p]!=='('&&t[p]!=='}'&&t[p]!=='{'){
      if(isNum(p)&&tail.length<3&&!tail.some(x=>typeof x==='string'))tail.push(num());
      else tail.push(tokStr(t[p++]));}
    const tn=tail.filter(x=>typeof x==='number');
    if(tn.length>0)f.cont=tn[0]|0; if(tn.length>1)f.flags=tn[1]|0; if(tn.length>2)f.val=tn[2];
    f.extra=tail.filter(x=>typeof x==='string').join(' ');
    if(/\bdetail\b/i.test(f.extra))f.cont|=CONTENTS_DETAIL;
    return f;
  }
  function patch(def3){
    expect('{');
    const P={tex:word(),w:0,h:0,cont:0,flags:0,val:0,sub:0,pts:null,def:def3?3:2};
    expect('(');
    const at=T.s[p-1];                                // the header, for a size error below
    const hdr=[];while(p<N&&t[p]!==')')hdr.push(tokStr(t[p++]));expect(')');
    const hn=[];for(let i=0;i<hdr.length;i++){if(/^subdivisions$/i.test(hdr[i])){P.sub=parseFloat(hdr[i+1])||0;i++;continue;}const v=parseFloat(hdr[i]);if(isFinite(v))hn.push(v);}
    P.w=hn[0]|0;P.h=hn[1]|0;
    const rest=def3?hn.slice(4):hn.slice(2);
    P.cont=(rest[0]||0)|0;P.flags=(rest[1]||0)|0;P.val=rest[2]||0;
    expect('(');
    const rows=[];
    while(p<N&&t[p]==='('){
      p++; const row=[];
      while(p<N&&t[p]==='('){p++;const v=[num(),num(),num(),num(),num()];expect(')');row.push(v);}
      expect(')'); rows.push(row);}
    expect(')');expect('}');
    const w=rows.length,h=w?rows[0].length:0;
    // the engine refuses a control grid over MAX_GRID_SIZE (129) points a side (cm_patch.c)
    if(w>129||h>129){const err=new Error('a patchDef of '+w+' x '+h+' points (the engine stops at 129)');err.off=at;throw err;}
    P.w=w;P.h=h;
    const pts=new Float64Array(w*h*5);
    for(let j=0;j<w;j++)for(let i=0;i<h;i++){const v=rows[j][i]||rows[j][rows[j].length-1];for(let k=0;k<5;k++)pts[(j*h+i)*5+k]=v[k];}
    P.pts=pts;
    return P;
  }
  function terrain(){
    expect('{');
    const at=(p<N)?T.s[p]:text.length;                // its size, for an error below
    const T2={W:num()|0,H:num()|0,fl:num()|0,org:[num(),num(),num()],corners:[],heights:null,hole1:null,hole2:null};
    // MOHAA writes 9 x 9; a size far past that is a damaged file, not a bigger block
    if(T2.W<2||T2.H<2||T2.W>257||T2.H>257){const err=new Error('a terrainDef of '+T2.W+' x '+T2.H+' points (MOHAA writes 9 x 9)');err.off=at;throw err;}
    expect('{');
    while(p<N&&t[p]!=='}'){
      const miss=num(),b2=num(); expect('(');
      const tx=word(); const v=[];while(p<N&&t[p]!==')')v.push(parseFloat(tokStr(t[p++]))||0); expect(')');
      T2.corners.push({miss:miss|0,b:b2,tex:tx,sh:[v[0]||0,v[1]||0],rot:v[2]||0,tw:v[3]||0,sc:[v[4]||1,v[5]||1],cont:(v[6]||0)|0,flags:(v[7]||0)|0});
    }
    expect('}');
    expect('{');
    const nv=T2.W*T2.H, hs=new Float64Array(nv), h1=new Uint8Array(nv), h2=new Uint8Array(nv);
    let k=0;
    while(p<N&&t[p]!=='}'){
      const hv=num(); let g=0;
      while(p<N&&t[p]==='('){p++;let nd=0;while(p<N&&t[p]!==')'){if(/^nodraw$/i.test(tokStr(t[p])))nd=1;p++;}expect(')');
        if(k<nv){if(g===0)h1[k]=nd;else if(g===1)h2[k]=nd;} g++;}
      if(k<nv)hs[k]=hv; k++;
    }
    expect('}');expect('}');
    T2.heights=hs;T2.hole1=h1;T2.hole2=h2;
    return T2;
  }
  while(p<N){
    if(t[p]!=='{'){p++;continue;}
    const e={kv:[],kvl:{},brushes:[],patches:[],terrains:[],prims:[],ts:T.s[p],te:0};
    p++;
    try{
      while(p<N&&t[p]!=='}'){
        if(t[p]==='{'){
          const ps=T.s[p], pi=p; p++;
          const kw=(typeof t[p]==='string')?t[p].toLowerCase():'';
          let prim=null;
          try{
            if(kw==='patchdef2'||kw==='patchdef3'){p++;prim={kind:1,d:patch(kw==='patchdef3')};expect('}');}
            else if(kw==='terraindef'){p++;prim={kind:2,d:terrain()};expect('}');}
            else if(kw==='brushdef'){p++;expect('{');const faces=[];while(p<N&&t[p]==='(')faces.push(face());expect('}');expect('}');prim={kind:0,d:{faces:faces}};}
            else{const faces=[];while(p<N&&t[p]==='(')faces.push(face());expect('}');prim={kind:0,d:{faces:faces}};}
          }catch(err){
            // which entity and primitive, where it starts and where it went wrong, and why
            errors.push({ent:ents.length,prim:e.prims.length,kind:kw==='terraindef'?'terrain block':(kw==='patchdef2'||kw==='patchdef3')?'patch':'brush',
              start:ps,off:(err.off!=null)?err.off:ps,msg:err.message});
            // resync: back to the primitive's "{" and past the "}" that closes it, so an
            // error inside a patch's or terrain block's inner { } doesn't end the entity
            p=pi;skipBlock();
            prim=null;
          }
          if(prim){prim.ts=ps;prim.te=T.e[p-1];prim.bn=e.prims.length;e.prims.push(prim);
            (prim.kind===0?e.brushes:prim.kind===1?e.patches:e.terrains).push(prim);}
          else e.prims.push(null);
        }else{
          const k=tokStr(t[p++]); const v=(p<N&&t[p]!=='}'&&t[p]!=='{')?tokStr(t[p++]):'';
          e.kv.push([k,v]); const kl=k.toLowerCase(); if(!(kl in e.kvl))e.kvl[kl]=v;
        }
      }
    }catch(err){errors.push({ent:ents.length,prim:-1,kind:'entity',start:e.ts,off:(err.off!=null)?err.off:e.ts,msg:err.message});}
    e.te=(p<N)?T.e[p]:text.length; p++;
    e.cls=(e.kvl.classname||'').toLowerCase();
    ents.push(e);
  }
  return {ents:ents,errors:errors};
}
// "$" and "#" in front of a key (SpawnArgs::SpawnInternal, g_spawn.cpp): when the entity's
// class has a setter of that name the value goes to it, so "$targetname" "x" names the
// entity just as "targetname" "x" does, and "#leash" "1792" sets its leash ("#" as a whole
// number, atoi). With no such setter it only sets a script variable of that name ("#set" is
// self.set), which no key stands for. The setters' names come with the page (D.sk:
// SETTER_KEYS in mohaa_bsp.py). Every key the page reads (kvl) goes by this, as in game:
// names, links and paths, labels, the lists; the info card shows the keys as written.
// An entity's keys are all posted for one moment and the event queue runs them last to first
// (Listener::PostEventInternal), so the first written of "name", "$name" and "#name" wins, as
// readMap keeps a key's first value. Plain "model" is due earlier (EV_PRIORITY_SPAWNARG), so
// "$model" wins over it; an actor's plain keys are due after its "$" and "#" ones
// (EV_SPAWNACTOR), so on an actor the plain key wins.
function spawnKeys(){
  const SK=new Set(D.sk||[]);if(!SK.size)return;
  const atoi=v=>{const n=parseInt(v,10);return String(isNaN(n)?0:n);};
  MAP.ents.forEach((e,ei)=>{
    const pre=new Map(),plain=new Map();   // name -> [where, value] of its first "$"/"#" form; -> where its first plain one
    e.kv.forEach(([k,v],i)=>{const kl=k.toLowerCase(),c=kl[0];
      if((c==='$'||c==='#')&&SK.has(kl.slice(1))){const n=kl.slice(1);if(!pre.has(n))pre.set(n,[i,c==='#'?atoi(v):v]);}
      else if(!plain.has(kl))plain.set(kl,i);});
    if(!pre.size)return;
    // an actor: by its class, else by the class its .tik spawns it as (as gameEnts)
    let actor=null;
    const isActor=()=>{if(actor===null){const g=GAME_CLASS[e.cls];
        if(g)actor=g==='actor';
        else{const mi=(D.modelOf||{})[ei],M=mi!=null?(D.models||[])[mi]:null;
          actor=!!(M&&M.cn&&GAME_CLASS[String(M.cn).toLowerCase()]==='actor');}}
      return actor;};
    // (a plain "model" is due before the rest, EV_PRIORITY_SPAWNARG, so "$model" outlasts it)
    for(const[n,[i,v]]of pre){const p=plain.get(n);if(p==null||(!isActor()&&(i<p||n==='model')))e.kvl[n]=v;}
  });
}

// ---- vector helpers ---------------------------------------------------------------
function vdot(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
function vcross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function vsub(a,b){return[a[0]-b[0],a[1]-b[1],a[2]-b[2]];}
function vnorm(v){const l=Math.hypot(v[0],v[1],v[2]);return l<1e-12?null:[v[0]/l,v[1]/l,v[2]/l];}

// The plane through a face's three points: normal = (p0-p1) x (p2-p1), the
// outward side of the brush (MapPlaneFromPoints in the map compiler).
function planeOf(f){
  const q=f.p, a=[q[0],q[1],q[2]], b=[q[3],q[4],q[5]], c=[q[6],q[7],q[8]];
  const n=vnorm(vcross(vsub(a,b),vsub(c,b)));
  if(!n)return null;
  return [n[0],n[1],n[2],vdot(a,n)];
}

// ---- brush windings: each face's polygon is a huge square on its plane, cut down
// by every other plane of the brush (polylib.c BaseWindingForPlane / ChopWinding).
const BOGUS=65536;
function baseWinding(n,d){
  const ax=(Math.abs(n[0])>=Math.abs(n[1])&&Math.abs(n[0])>=Math.abs(n[2]))?0:(Math.abs(n[1])>=Math.abs(n[2])?1:2);
  let up=(ax===2)?[1,0,0]:[0,0,1];
  const dd=vdot(up,n); up=vnorm([up[0]-dd*n[0],up[1]-dd*n[1],up[2]-dd*n[2]]);
  if(!up)return null;
  const rt=vcross(up,n), o=[n[0]*d,n[1]*d,n[2]*d], R=BOGUS;
  return[o[0]-rt[0]*R+up[0]*R,o[1]-rt[1]*R+up[1]*R,o[2]-rt[2]*R+up[2]*R,
         o[0]+rt[0]*R+up[0]*R,o[1]+rt[1]*R+up[1]*R,o[2]+rt[2]*R+up[2]*R,
         o[0]+rt[0]*R-up[0]*R,o[1]+rt[1]*R-up[1]*R,o[2]+rt[2]*R-up[2]*R,
         o[0]-rt[0]*R-up[0]*R,o[1]-rt[1]*R-up[1]*R,o[2]-rt[2]*R-up[2]*R];
}
// Keep the part of polygon w (flat x,y,z list) behind the plane.
function clipWinding(w,nx,ny,nz,d,eps){
  const m=w.length/3, ds=new Float64Array(m);
  let front=false,back=false;
  for(let i=0;i<m;i++){const v=w[i*3]*nx+w[i*3+1]*ny+w[i*3+2]*nz-d;ds[i]=v;if(v>eps)front=true;else if(v<-eps)back=true;}
  if(!front)return w;
  if(!back)return null;
  const out=[];
  for(let i=0;i<m;i++){
    const d1=ds[i], j=(i+1)%m, d2=ds[j];
    if(d1<=eps)out.push(w[i*3],w[i*3+1],w[i*3+2]);
    if((d1>eps&&d2<-eps)||(d1<-eps&&d2>eps)){
      const tt=d1/(d1-d2);
      out.push(w[i*3]+tt*(w[j*3]-w[i*3]),w[i*3+1]+tt*(w[j*3+1]-w[i*3+1]),w[i*3+2]+tt*(w[j*3+2]-w[i*3+2]));}
  }
  return out.length>=9?out:null;
}
function windingArea(w){
  const m=w.length/3; let ax=0,ay=0,az=0;
  for(let i=1;i+1<m;i++){
    const ux=w[i*3]-w[0],uy=w[i*3+1]-w[1],uz=w[i*3+2]-w[2],vx=w[i*3+3]-w[0],vy=w[i*3+4]-w[1],vz=w[i*3+5]-w[2];
    ax+=uy*vz-uz*vy; ay+=uz*vx-ux*vz; az+=ux*vy-uy*vx;}
  return 0.5*Math.hypot(ax,ay,az);
}
// Polygons of a brush given its planes [nx,ny,nz,d] (null planes give null).
// Bevel and duplicate planes come back as null: they have no face.
function brushWindings(planes){
  const out=new Array(planes.length);
  for(let i=0;i<planes.length;i++){
    const P=planes[i]; if(!P){out[i]=null;continue;}
    let w=baseWinding(P,P[3]);
    for(let j=0;j<planes.length&&w;j++){
      if(j===i)continue; const Q=planes[j]; if(!Q)continue;
      if(P[0]*Q[0]+P[1]*Q[1]+P[2]*Q[2]>0.999999&&Math.abs(P[3]-Q[3])<0.001){if(j<i)w=null;continue;}
      w=clipWinding(w,Q[0],Q[1],Q[2],Q[3],0.01);
    }
    out[i]=(w&&windingArea(w)>=0.01)?w:null;
  }
  return out;
}

// ---- texture projection (q3map map.c TextureAxisFromPlane / QuakeTextureVecs) -------
// normal, s axis, t axis for floor, ceiling, west, east, south and north walls
const BASE_AXIS=[0,0,1, 1,0,0, 0,-1,0,   0,0,-1, 1,0,0, 0,-1,0,   1,0,0, 0,1,0, 0,0,-1,
                 -1,0,0, 0,1,0, 0,0,-1,  0,1,0, 1,0,0, 0,0,-1,    0,-1,0, 1,0,0, 0,0,-1];
function texVecs(n,shift,rot,scale){
  let best=0,bi=0;
  for(let i=0;i<6;i++){const d=n[0]*BASE_AXIS[i*9]+n[1]*BASE_AXIS[i*9+1]+n[2]*BASE_AXIS[i*9+2];if(d>best){best=d;bi=i;}}
  const xv=BASE_AXIS.slice(bi*9+3,bi*9+6), yv=BASE_AXIS.slice(bi*9+6,bi*9+9);
  const sx=scale[0]||1, sy=scale[1]||1;
  let s,c;
  if(rot===0){s=0;c=1;}else if(rot===90){s=1;c=0;}else if(rot===180){s=0;c=-1;}else if(rot===270){s=-1;c=0;}
  else{const a=rot/180*Math.PI;s=Math.sin(a);c=Math.cos(a);}
  const sv=xv[0]?0:(xv[1]?1:2), tv=yv[0]?0:(yv[1]?1:2);
  const vs=[xv,yv].map(v=>{const r=v.slice();const ns=c*r[sv]-s*r[tv],nt=s*r[sv]+c*r[tv];r[sv]=ns;r[tv]=nt;return r;});
  return [vs[0][0]/sx,vs[0][1]/sx,vs[0][2]/sx,shift[0], vs[1][0]/sy,vs[1][1]/sy,vs[1][2]/sy,shift[1]];
}
// Brush primitives (brushDef): the texture matrix works on the face's own axes.
function bpAxes(n){
  let nx=Math.abs(n[0])<1e-6?0:n[0], ny=Math.abs(n[1])<1e-6?0:n[1], nz=Math.abs(n[2])<1e-6?0:n[2];
  const RotY=-Math.atan2(nz,Math.sqrt(ny*ny+nx*nx)), RotZ=Math.atan2(ny,nx);
  return [[-Math.sin(RotZ),Math.cos(RotZ),0],[-Math.sin(RotY)*Math.cos(RotZ),-Math.sin(RotY)*Math.sin(RotZ),-Math.cos(RotY)]];
}

// ---- Bezier patches: each 3x3 block of control points is a biquadratic surface ----
function patchFlat(P,j0,i0){
  // how far the middle control points stray from the straight line between corners
  const h=P.h, q=P.pts; let dev=0;
  const pt=(j,i,k)=>q[((j0+j)*h+(i0+i))*5+k];
  for(let r=0;r<3;r++)for(let k=0;k<2;k++){
    // along i
    let a=[pt(r,0,0),pt(r,0,1),pt(r,0,2)], m=[pt(r,1,0),pt(r,1,1),pt(r,1,2)], b=[pt(r,2,0),pt(r,2,1),pt(r,2,2)];
    if(k===1){a=[pt(0,r,0),pt(0,r,1),pt(0,r,2)];m=[pt(1,r,0),pt(1,r,1),pt(1,r,2)];b=[pt(2,r,0),pt(2,r,1),pt(2,r,2)];}
    const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2,(a[2]+b[2])/2];
    dev=Math.max(dev,Math.hypot(m[0]-mid[0],m[1]-mid[1],m[2]-mid[2]));
  }
  return dev;
}
// Grid of vertices for a whole patch: returns {cols, rows, v: Float64Array(x,y,z,s,t)}.
// X, if given, holds xn more numbers per control point (in the same order as P.pts),
// carried through the same curves into x (lightmap coordinates and vertex light).
function tessPatch(P,X,xn){
  const w=P.w, h=P.h;
  if(w<3||h<3||!(w&1)||!(h&1))return null;
  const bj=(w-1)/2, bi=(h-1)/2;
  // one subdivision level per block row / column, from how curved it is
  const lj=new Array(bj).fill(1), li=new Array(bi).fill(1);
  for(let a=0;a<bj;a++)for(let b=0;b<bi;b++){
    const dev=patchFlat(P,a*2,b*2);
    const L=dev<0.1?1:Math.min(16,Math.max(3,Math.ceil(Math.sqrt(dev)*1.5)));
    lj[a]=Math.max(lj[a],L); li[b]=Math.max(li[b],L);}
  const cols=lj.reduce((x,y)=>x+y,0)+1, rows=li.reduce((x,y)=>x+y,0)+1;
  const v=new Float64Array(cols*rows*5), x=X?new Float64Array(cols*rows*xn):null;
  const q=P.pts;
  const B=(u,k0,k1,k2)=>{const iu=1-u;return iu*iu*k0+2*u*iu*k1+u*u*k2;};
  let cj=0;
  for(let a=0;a<bj;a++){
    const nj=lj[a]+(a===bj-1?1:0);
    for(let sj=0;sj<nj;sj++){
      const u=sj/lj[a];
      let ci=0;
      for(let b=0;b<bi;b++){
        const ni=li[b]+(b===bi-1?1:0);
        for(let si=0;si<ni;si++){
          const vv=si/li[b], o=((cj)*rows+ci)*5;
          for(let k=0;k<5;k++){
            const c=r=>B(vv,q[((a*2+r)*h+b*2)*5+k],q[((a*2+r)*h+b*2+1)*5+k],q[((a*2+r)*h+b*2+2)*5+k]);
            v[o+k]=B(u,c(0),c(1),c(2));
          }
          if(x){const ox=((cj)*rows+ci)*xn;
            for(let k=0;k<xn;k++){
              const c=r=>B(vv,X[((a*2+r)*h+b*2)*xn+k],X[((a*2+r)*h+b*2+1)*xn+k],X[((a*2+r)*h+b*2+2)*xn+k]);
              x[ox+k]=B(u,c(0),c(1),c(2));
            }}
          ci++;
        }
      }
      cj++;
    }
  }
  return {cols:cols,rows:rows,v:v,x:x};
}

// ---- terrain: which two triangles each square splits into (cm_terrain.c) --------
// Squares alternate their diagonal in a checkerboard; the first triangle is the one on
// the square's +x edge, the second the one on its -x edge, matching the two
// "( nodraw )" groups each vertex line of a terrainDef carries.
function terrainTris(i,j){
  if((i+j)&1)return[[i+1,j],[i+1,j+1],[i,j+1], [i,j],[i+1,j],[i,j+1]];
  return[[i,j],[i+1,j],[i+1,j+1], [i,j],[i+1,j+1],[i,j+1]];
}

// ---- entity helpers ------------------------------------------------------------------
function parseVec(s,n){
  if(s==null)return null;
  const v=String(s).trim().split(/\s+/).map(Number);
  if(v.length<n||v.slice(0,n).some(x=>!isFinite(x)))return null;
  return v.slice(0,n);
}
// The entity's rotation from "angles" (pitch yaw roll) or "angle" (yaw, with -1 up and
// -2 down), as the engine's AnglesToAxis: columns forward, left, up.
function entAngles(kvl){
  let a=parseVec(kvl.angles,3);
  if(!a){const y=parseFloat(kvl.angle);
    if(isFinite(y)){if(y===-1)a=[-90,0,0];else if(y===-2)a=[90,0,0];else a=[0,y,0];}}
  return a||[0,0,0];
}
function anglesAxis(a){
  const D=Math.PI/180, sp=Math.sin(a[0]*D),cp=Math.cos(a[0]*D),sy=Math.sin(a[1]*D),cy=Math.cos(a[1]*D),sr=Math.sin(a[2]*D),cr=Math.cos(a[2]*D);
  const f=[cp*cy,cp*sy,-sp], l=[sr*sp*cy-cr*sy,sr*sp*sy+cr*cy,sr*cp], u=[cr*sp*cy+sr*sy,cr*sp*sy-sr*cy,cr*cp];
  return [f,l,u];
}
// Classes the compiler folds into the world: picking one of their brushes picks the
// brush, as for world brushes.
const WORLDLIKE={worldspawn:1,detail:1,func_group:1,func_detail:1};

// ---- scene -------------------------------------------------------------------------
// buildScene() turns the parsed map into flat arrays ready for WebGL:
//   vertices (position, texture coordinate, pick id),
//   "faces" - the pickable units: one per brush face, patch or terrain block - with
//   their entity, primitive, texture, category bits and their ranges in the vertex,
//   triangle and edge lists.
// texFor(name) gives the texture entry for a .map texture name (adding a stand-in for
// names the build didn't know).
function buildScene(map,texFor,progress){
  const ents=map.ents;
  const P=[],U=[],K=[], TRI=[], EDG=[];
  const F={ent:[],prim:[],side:[],tex:[],v0:[],vn:[],i0:[],in:[],e0:[],en:[],cat:[],kind:[],n:[]};
  const prims=[];                        // {ent, bn, kind, f0, f1, mins, maxs, origin?}
  const entInfo=[];
  let nf=0;
  function addFace(ei,pi,side,ti,cat,kind,n){
    F.ent.push(ei);F.prim.push(pi);F.side.push(side);F.tex.push(ti);F.v0.push(P.length/3);F.vn.push(0);
    F.i0.push(TRI.length);F.in.push(0);F.e0.push(EDG.length);F.en.push(0);F.cat.push(cat);F.kind.push(kind);F.n.push(n||null);
    return nf++;
  }
  function closeFace(fi){F.vn[fi]=P.length/3-F.v0[fi];F.in[fi]=TRI.length-F.i0[fi];F.en[fi]=EDG.length-F.e0[fi];}
  const groupCat={caulk:C_CAULK,clip:C_CLIP,trigger:C_TRIGGER,hint:C_HINT,skip:C_HINT,origin:C_ORIGIN,
                  portal:C_PORTAL,nodraw:C_NODRAW,ladder:C_NODRAW,liquid:C_LIQUID,fog:C_LIQUID};
  function texCat(te,cont){
    let c=0;
    if(te.g&&groupCat[te.g])c|=groupCat[te.g];
    if(te.f&TF_SKY)c|=C_SKY;
    if((te.f&(TF_BLEND|TF_ADD))||((te.cf||0)&CONTENTS_TRANSLUCENT&&!(te.f&TF_NODRAW)))c|=C_TRANS;
    if(cont&CONTENTS_CLIPS&&(te.f&TF_NODRAW))c|=C_CLIP;
    if(cont&CONTENTS_ORIGIN)c|=C_ORIGIN;
    if(cont&CONTENTS_AREAPORTAL)c|=C_PORTAL;
    if(cont&CONTENTS_LIQUID)c|=C_LIQUID;
    if(/(^|\/)vis/.test(te.n||'')&&te.g==='hint')c|=C_VIS;
    // Any other surface the game never draws is editor-only too, such as the flat tree
    // pictures (misc_outside/commontreeshadow) that only cast a tree's shadow.
    if((te.f&TF_NODRAW)&&!(c&~C_TRANS))c=C_NODRAW;
    // rain volumes and foliage clips are shown and hidden on their own
    if((c&C_NODRAW)&&/(^|\/)common\/rain$/i.test(te.n||''))c=(c&~C_NODRAW)|C_RAIN;
    if((c&C_CLIP)&&/(^|\/)common\/foliageclip$/i.test(te.n||''))c=(c&~C_CLIP)|C_FOLIAGE;
    return c;
  }
  let lastTick=0, done=0;
  const total=ents.reduce((s,e)=>s+e.prims.length,0)||1;
  for(let ei=0;ei<ents.length;ei++){
    const e=ents[ei];
    const worldlike=!!WORLDLIKE[e.cls];
    const trig=e.cls.startsWith('trigger_');
    const info={mins:[Infinity,Infinity,Infinity],maxs:[-Infinity,-Infinity,-Infinity],originBrush:null,nBrush:0};
    entInfo.push(info);
    for(let bn=0;bn<e.prims.length;bn++){
      const pr=e.prims[bn]; done++;
      if(progress&&done-lastTick>2000){lastTick=done;progress(done/total);}
      if(!pr)continue;
      const rec={ent:ei,bn:bn,kind:pr.kind,f0:nf,f1:nf,mins:[Infinity,Infinity,Infinity],maxs:[-Infinity,-Infinity,-Infinity]};
      const grow=(x,y,z)=>{if(x<rec.mins[0])rec.mins[0]=x;if(y<rec.mins[1])rec.mins[1]=y;if(z<rec.mins[2])rec.mins[2]=z;
                           if(x>rec.maxs[0])rec.maxs[0]=x;if(y>rec.maxs[1])rec.maxs[1]=y;if(z>rec.maxs[2])rec.maxs[2]=z;};
      const pi=prims.length;
      if(pr.kind===0){                                  // ---- brush
        const faces=pr.d.faces;
        const planes=faces.map(planeOf);
        const wins=brushWindings(planes);
        let allOrigin=faces.length>0, detail=e.cls==='detail';
        for(const f of faces){if(!/(^|\/)origin$/i.test(f.tex))allOrigin=false;if(f.cont&CONTENTS_DETAIL)detail=true;}
        for(let k=0;k<faces.length;k++){
          const w=wins[k]; if(!w)continue;
          const f=faces[k], pl=planes[k], te=texFor(f.tex), ti=te.i;
          let cat=worldlike?(detail?C_DETAIL:C_WORLD):C_ENTBRUSH;
          if(trig)cat|=C_TRIGGER;
          cat|=texCat(te,f.cont);
          if(allOrigin)cat|=C_ORIGIN;
          if(detail&&!worldlike)cat|=C_DETAIL;
          const fi=addFace(ei,pi,k,ti,cat,0,pl);
          const v0=P.length/3, m=w.length/3;
          let vs=null;
          if(f.tm){const ax=bpAxes(pl);vs=[ax,f.tm];}
          else vs=texVecs(pl,f.sh,f.rot,f.sc);
          const tw=te.w||64, th=te.h||64;
          for(let q=0;q<m;q++){
            const x=w[q*3],y=w[q*3+1],z=w[q*3+2];
            P.push(x,y,z); grow(x,y,z);
            if(f.tm){const a=vs[0],tm=vs[1];const u=x*a[0][0]+y*a[0][1]+z*a[0][2], vv=x*a[1][0]+y*a[1][1]+z*a[1][2];
              U.push(tm[0][0]*u+tm[0][1]*vv+tm[0][2], tm[1][0]*u+tm[1][1]*vv+tm[1][2]);}
            else U.push((x*vs[0]+y*vs[1]+z*vs[2]+vs[3])/tw,(x*vs[4]+y*vs[5]+z*vs[6]+vs[7])/th);
            K.push(fi+1);
          }
          for(let q=1;q+1<m;q++)TRI.push(v0,v0+q,v0+q+1);
          for(let q=0;q<m;q++)EDG.push(v0+q,v0+(q+1)%m);
          closeFace(fi);
        }
        if(allOrigin&&isFinite(rec.mins[0]))info.originBrush=[(rec.mins[0]+rec.maxs[0])/2,(rec.mins[1]+rec.maxs[1])/2,(rec.mins[2]+rec.maxs[2])/2];
        else if(isFinite(rec.mins[0])){info.nBrush++;
          for(let k=0;k<3;k++){info.mins[k]=Math.min(info.mins[k],rec.mins[k]);info.maxs[k]=Math.max(info.maxs[k],rec.maxs[k]);}}
        rec.origin=allOrigin;
      }else if(pr.kind===1){                            // ---- patch
        const Pd=pr.d, te=texFor(Pd.tex), g=tessPatch(Pd);
        if(g){
          let cat=(worldlike?0:C_ENTBRUSH)|C_PATCH|texCat(te,Pd.cont);
          if(trig)cat|=C_TRIGGER;
          const fi=addFace(ei,pi,-1,te.i,cat,1,null);
          const v0=P.length/3;
          for(let q=0;q<g.cols*g.rows;q++){const o=q*5;P.push(g.v[o],g.v[o+1],g.v[o+2]);U.push(g.v[o+3],g.v[o+4]);K.push(fi+1);grow(g.v[o],g.v[o+1],g.v[o+2]);}
          const R=g.rows;
          for(let a=0;a+1<g.cols;a++)for(let b=0;b+1<R;b++){
            const i00=v0+a*R+b,i01=v0+a*R+b+1,i10=v0+(a+1)*R+b,i11=v0+(a+1)*R+b+1;
            // both windings: a patch is seen from either side
            TRI.push(i00,i10,i11, i00,i11,i01, i00,i11,i10, i00,i01,i11);}
          for(let a=0;a<g.cols;a++)for(let b=0;b<R;b++){
            if(a+1<g.cols&&(b===0||b===R-1))EDG.push(v0+a*R+b,v0+(a+1)*R+b);
            if(b+1<R&&(a===0||a===g.cols-1))EDG.push(v0+a*R+b,v0+a*R+b+1);}
          closeFace(fi);
        }
        if(isFinite(rec.mins[0])){info.nBrush++;for(let k=0;k<3;k++){info.mins[k]=Math.min(info.mins[k],rec.mins[k]);info.maxs[k]=Math.max(info.maxs[k],rec.maxs[k]);}}
      }else{                                            // ---- terrain
        const Td=pr.d, W=Td.W, H=Td.H, ox=Td.org[0], oy=Td.org[1], oz=Td.org[2];
        const nbx=Math.max(1,(W-1)>>3), nby=Math.max(1,(H-1)>>3);
        // one texture per 8x8 block, from the corner line at the block's lowest corner
        const corner=(bx,by)=>Td.corners[by*(nbx+1)+bx]||Td.corners[0]||{tex:'common/caulk',sh:[0,0],rot:0,tw:0,sc:[1,1],cont:0,miss:0};
        const byTex=new Map();
        for(let j=0;j+1<H;j++)for(let i=0;i+1<W;i++){
          const bx=Math.min(nbx-1,i>>3), by=Math.min(nby-1,j>>3), c=corner(bx,by);
          if(c.miss)continue;
          let L=byTex.get(c.tex); if(!L){L=[];byTex.set(c.tex,L);} L.push(i,j,bx,by);
        }
        for(const [tex,L] of byTex){
          const te=texFor(tex), c0=corner(L[2],L[3]);
          const cat=(worldlike?0:C_ENTBRUSH)|C_TERRAIN|texCat(te,c0.cont);
          const fi=addFace(ei,pi,-1,te.i,cat,2,[0,0,1,0]);
          const vmap=new Map(); const v0=P.length/3;
          const vert=(i,j,c)=>{const key=j*W+i; let id=vmap.get(key);
            if(id===undefined){id=P.length/3;vmap.set(key,id);
              const x=ox+i*64,y=oy+j*64,z=oz+Td.heights[key];
              P.push(x,y,z);grow(x,y,z);K.push(fi+1);
              const vs=texVecs([0,0,1],c.sh,c.rot,c.sc), tw=c.tw||te.w||64, th=c.tw?c.tw*((te.h||64)/(te.w||64)):(te.h||64);
              const rx=x-ox, ry=y-oy;
              U.push((rx*vs[0]+ry*vs[1]+vs[3])/tw,(rx*vs[4]+ry*vs[5]+vs[7])/th);}
            return id;};
          for(let q=0;q<L.length;q+=4){
            const i=L[q],j=L[q+1],c=corner(L[q+2],L[q+3]), k=j*W+i, tr=terrainTris(i,j);
            const holes=[Td.hole1[k],Td.hole2[k]];
            for(let s=0;s<2;s++){
              if(holes[s])continue;
              const a=vert(tr[s*3][0],tr[s*3][1],c), b=vert(tr[s*3+1][0],tr[s*3+1][1],c), d=vert(tr[s*3+2][0],tr[s*3+2][1],c);
              TRI.push(a,d,b);                          // clockwise seen from above
              EDG.push(a,b,b,d,d,a);
            }
          }
          if(P.length/3===v0){nf--;for(const k in F)F[k].pop();continue;}
          closeFace(fi);
        }
        if(isFinite(rec.mins[0])){info.nBrush++;for(let k=0;k<3;k++){info.mins[k]=Math.min(info.mins[k],rec.mins[k]);info.maxs[k]=Math.max(info.maxs[k],rec.maxs[k]);}}
      }
      rec.f1=nf;
      prims.push(rec);
    }
  }
  const nv=P.length/3;
  const out={
    nv:nv, pos:new Float32Array(P), uv:new Float32Array(U), pick:new Float32Array(K),
    tri:new Uint32Array(TRI), edge:new Uint32Array(EDG),
    nf:nf, faceEnt:Int32Array.from(F.ent), facePrim:Int32Array.from(F.prim), faceSide:Int32Array.from(F.side),
    faceTex:Int32Array.from(F.tex), faceV0:Uint32Array.from(F.v0), faceVN:Uint32Array.from(F.vn),
    faceI0:Uint32Array.from(F.i0), faceIN:Uint32Array.from(F.in), faceE0:Uint32Array.from(F.e0), faceEN:Uint32Array.from(F.en),
    faceCat:Uint32Array.from(F.cat), faceKind:Uint8Array.from(F.kind), facePlane:F.n,
    prims:prims, entInfo:entInfo
  };
  return out;
}
/*CORE-END*/

// ============================================================================
//  The page
// ============================================================================
const $=id=>document.getElementById(id);
const TITLE=__TITLE_JS__;
const FORCETHEME='__THEME__';
const LS={get(k){try{return localStorage.getItem(k);}catch(_e){return null;}},
          set(k,v){try{if(v==null)localStorage.removeItem(k);else localStorage.setItem(k,v);}catch(_e){}}};
// Slider values (camera speed, fov, cubic clip distance, grid size, trim step, follow-camera
// zoom) are kept in the launcher's config when embedded, and in localStorage otherwise.
let SL_READY=false,SL_T=0;
function slidersState(){return {speed:moveSpeed,fov:fovX,clipD:clipDist,gridSz:GRID.i,modStep:MOD.stepI,simZoom:+$('simZoom').value};}
function slidersPost(){
  if(!SL_READY)return;clearTimeout(SL_T);
  SL_T=setTimeout(()=>{const o=slidersState();LS.set('mohaaMapViewerSliders',JSON.stringify(o));
    try{if(window.chrome&&window.chrome.webview)window.chrome.webview.postMessage('mohaa-sliders\n'+JSON.stringify(o));}catch(_e){}},300);}
window.MOHAA_SLIDERS=function(o,ready){
  try{
    if(o&&typeof o==='object'){
      if(o.speed>0){moveSpeed=Math.max(50,Math.min(3000,+o.speed));$('speed').value=moveSpeed;$('speedV').textContent=moveSpeed;}
      if(o.fov>0){fovX=Math.max(60,Math.min(150,+o.fov));$('fov').value=fovX;$('fovV').textContent=fovX;}
      if(o.clipD>0)setClipDist(+o.clipD);
      if(o.gridSz!=null&&isFinite(o.gridSz))setGridSize(+o.gridSz,true);
      if(o.modStep!=null&&isFinite(o.modStep)){MOD.stepI=Math.max(0,Math.min(MOD_STEPS.length-1,o.modStep|0));$('modStep').value=MOD.stepI;$('modStepV').textContent=MOD_STEPS[MOD.stepI];}
      if(o.simZoom!=null&&isFinite(o.simZoom)){$('simZoom').value=Math.max(0,Math.min(100,+o.simZoom));simZoomShow();}
      requestDraw();
    }
  }catch(_e){}
  if(ready)SL_READY=true;
};
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
// Numbers the way MOHAA scripts and .map files write them: plain integers, else up to 2 decimals.
function fnum(x){if(!isFinite(x))return '0';const r=Math.round(x);if(Math.abs(x-r)<0.005)return String(r===0?0:r);
  return (Math.round(x*100)/100).toString();}
function fvec(v){return '( '+v.map(fnum).join(' ')+' )';}
function copyCursorPos(){
  const[x,y]=hoverAt;const h=hitInfo(pickAt(x,y),x,y);
  let p=h&&h.point;
  if(!p&&h&&h.ent>0&&ENTS[h.ent])p=ENTS[h.ent].origin||ENTS[h.ent].anchor;      // a marker: its origin
  if(!p){flash('Nothing under the cursor to copy (the sky or the void)');return;}
  const t='( '+p.map(v=>fnum(Math.round(v*100)/100)).join(' ')+' )';
  copyText(t,'Mouse cursor\'s origin '+t+' copied to the clipboard');
}
function copyText(s,msg){
  const done=()=>flash(msg||'Copied to the clipboard');
  try{if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(s).then(done,()=>fallback());return;}}catch(_e){}
  fallback();
  function fallback(){const ta=document.createElement('textarea');ta.value=s;ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(_e){}ta.remove();}
}
let _flashT=null,_flashLog='',_flashLogT=0;
// a note in the status line, for a moment; the same line goes in the launcher's Output pane
// too (in a browser, the console), once: the same note again within 2 s (a held key, a
// repeated click) isn't written again
function flash(msg){const h=$('hintHover');h.textContent=msg;h.style.color='var(--accent)';
  clearTimeout(_flashT);_flashT=setTimeout(()=>{h.style.color='';h.textContent='';},1600);
  const s=String(msg==null?'':msg),now=performance.now();
  if(s&&(s!==_flashLog||now-_flashLogT>2000))hostLog('ok',s);
  _flashLog=s;_flashLogT=now;}

// Side-panel collapse tab (wired first so it works even if the map fails to load).
{const tab=$('sideTab'),side=$('side');
 tab.onclick=()=>{const hide=side.style.display!=='none';side.style.display=hide?'none':'flex';
   tab.innerHTML=hide?'&#10094;':'&#10095;';tab.title=(hide?'Expand':'Collapse')+' the control panel (\\)';
   window.dispatchEvent(new Event('resize'));};}

// ---- theme + backdrop ----------------------------------------------------------
const TH={bg:[0.055,0.067,0.086],sel:'#ff4d4d',accent:'#7ee787',labelbg:'8,11,16',txt:'#d6dde6',dim:'#8b97a6'};
function cssVar(n){try{return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}catch(e){return '';}}
function hexRGB(h){h=(h||'').replace('#','');if(h.length===3)h=h.split('').map(c=>c+c).join('');const v=parseInt(h,16);
  return isFinite(v)?[(v>>16&255)/255,(v>>8&255)/255,(v&255)/255]:[0,0,0];}
function readTheme(){TH.bg=hexRGB(cssVar('--bg'));TH.sel=cssVar('--selcol')||TH.sel;TH.accent=cssVar('--accent')||TH.accent;
  TH.labelbg=cssVar('--labelbg')||TH.labelbg;TH.txt=cssVar('--txt')||TH.txt;TH.dim=cssVar('--dim')||TH.dim;}
const themeBtn=$('bTheme');
function setTheme(light){document.documentElement.classList.toggle('light',light);
  themeBtn.innerHTML=light?'☽ Dark mode':'☀ Light mode';
  LS.set('mohaaViewerTheme',light?'light':'dark');
  readTheme();
  try{const b=$('bgcol');if(b&&!document.documentElement.style.getPropertyValue('--bg'))b.value=cssVar('--bg')||b.value;}catch(_e){}
  try{if(typeof GRID!=='undefined'){GRID.key='';if(!GRID.col)$('gridcol').value=gridDefCol();}}catch(_e){}
  requestDraw();}
themeBtn.onclick=()=>setTheme(!document.documentElement.classList.contains('light'));
const bgIn=$('bgcol');
function applyBackdrop(col,save){
  if(col)document.documentElement.style.setProperty('--bg',col);else document.documentElement.style.removeProperty('--bg');
  if(save)LS.set('mohaaMapViewerBg',col||null);
  readTheme();bgIn.value=cssVar('--bg')||bgIn.value;requestDraw();}
bgIn.oninput=()=>applyBackdrop(bgIn.value,true);bgIn.onchange=bgIn.oninput;
$('bgReset').onclick=()=>{applyBackdrop(null,true);gridColour(null);};

// ---- grid (+) -----------------------------------------------------------------------
// MOHRadiant's grid sizes, 1 to 512 units. In 3D it is a lattice of lines a grid size apart
// round a point (Modify's moving or selected entity, else ahead of the camera), fading out
// over a dozen cells or so so the map stays in sight, with its coordinates written along
// the three lines through that point. On, Modify's Add and Move snap to its corners.
const GRID={on:false,i:3,mode:'xy',col:null,key:'',n:0,buf:null,vao:null,prog:null,c:null,N:0,fk:'',fp:null,vis:new Map(),vk:''};
function gridSize(){return 1<<GRID.i;}
function gridDefCol(){return '#6fd6e8';}   // a cyan the map's own colours rarely are
function gridSave(){slidersPost();LS.set('mohaaMapViewerGrid',JSON.stringify({on:GRID.on,i:GRID.i,col:GRID.col,mode:GRID.mode}));}
// the planes drawn: one plane across two axes (its normal the third), or all three
const GRID_MODES=['xy','xz','yz','all'];
function gridNormal(){return GRID.mode==='xy'?2:GRID.mode==='xz'?1:GRID.mode==='yz'?0:-1;}
function gridModeBtn(){$('bGrid').textContent='Grid '+(GRID.mode==='all'?'all':GRID.mode.toUpperCase());}
function setGridMode(m,quiet){GRID.mode=GRID_MODES.includes(m)?m:'xy';gridModeBtn();GRID.key='';gridSave();requestDraw();
  if(!quiet)flash('Grid '+(GRID.mode==='all'?'all: the whole 3D lattice':GRID.mode.toUpperCase()+': one plane')+(GRID.on?'':' (Grid is off: + turns it on)'));}
function gridColour(c,save){GRID.col=c||null;$('gridcol').value=GRID.col||gridDefCol();GRID.key='';if(save!==false)gridSave();requestDraw();}
function setGrid(on){GRID.on=!!on;{const b=$('d_grid');if(b)b.classList.toggle('on',GRID.on);}GRID.key='';gridSave();requestDraw();
  flash(GRID.on?'Grid '+gridSize()+' on: Modify\'s Add and Move snap to it ({ and } change the size)':'Grid off');}
function setGridSize(i,quiet){GRID.i=Math.max(0,Math.min(9,i|0));$('gridSz').value=GRID.i;$('gridV').textContent=gridSize();
  GRID.key='';gridSave();requestDraw();if(!quiet)flash('Grid size '+gridSize()+(GRID.on?'':' (Grid is off: + turns it on)'));}
$('bGrid').onclick=()=>setGridMode(GRID_MODES[(GRID_MODES.indexOf(GRID.mode)+1)%GRID_MODES.length]);
$('gridSz').oninput=()=>setGridSize(+$('gridSz').value);
$('gridcol').oninput=()=>gridColour($('gridcol').value);$('gridcol').onchange=$('gridcol').oninput;
function gridLoad(){let g=null;try{g=JSON.parse(LS.get('mohaaMapViewerGrid')||'null');}catch(_e){}
  if(g){GRID.on=!!g.on;GRID.i=g.i==null?3:g.i;GRID.col=g.col||null;GRID.mode=GRID_MODES.includes(g.mode)?g.mode:'xy';}
  {const b=$('d_grid');if(b)b.classList.toggle('on',GRID.on);}gridModeBtn();setGridSize(GRID.i,true);gridColour(GRID.col,false);}
function gridSnap(v){const g=gridSize();return Math.round(v/g)*g;}
// where the lattice is centred
function gridFocus(){
  if(MOD.placing&&MOD.ghost)return MOD.ghost;
  if(MOD.sel>=0&&MOD.ents[MOD.sel]&&modDrawn(MOD.sel))return modOrigin(MOD.ents[MOD.sel]);
  // else what the camera looks at: the first surface straight ahead (a little this side of
  // it), or a point ahead when there is none near
  const a=camAxes(),key=cam.pos.map(v=>Math.round(v)).join(',')+'|'+a.f.map(v=>v.toFixed(3)).join(',');
  if(GRID.fk===key)return GRID.fp;
  let d=Math.min(Math.max(gridSize()*5,96),3000);
  try{const L=4096,e=[cam.pos[0]+a.f[0]*L,cam.pos[1]+a.f[1]*L,cam.pos[2]+a.f[2]*L],t=pgTrace(cam.pos,e,[0,0,0],[0,0,0],false);
    if(t&&!t.startsolid&&t.f<1)d=Math.max(8,t.f*L-2);}catch(_e){}
  GRID.fk=key;GRID.fp=[cam.pos[0]+a.f[0]*d,cam.pos[1]+a.f[1]*d,cam.pos[2]+a.f[2]*d];
  return GRID.fp;
}
// whether the camera sees a point (nothing solid between): the grid's numbers behind a
// floor or a wall aren't written
function gridSees(p){
  const k=p.join(',');let v=GRID.vis.get(k);if(v!=null)return v;
  try{const t=pgTrace(cam.pos,p,[0,0,0],[0,0,0],false);v=!(t&&(t.startsolid||t.f<0.995));}catch(_e){v=true;}
  GRID.vis.set(k,v);return v;
}
// cells each way: a single plane has room for more than the whole lattice
function gridCells(){return gridNormal()>=0?Math.max(8,Math.min(24,Math.round(384/gridSize()))):Math.max(6,Math.min(12,Math.round(192/gridSize())));}
function drawGrid(vp){
  if(!GRID.on||!gl)return;
  const g=gridSize(),N=gridCells(),f=gridFocus(),c=[gridSnap(f[0]),gridSnap(f[1]),gridSnap(f[2])],nm=gridNormal();
  // one plane: the grid line nearest the point on the camera's side of it, so a plane
  // laid on a floor or a wall is just in front of it, not inside
  if(nm>=0){const k=f[nm]/g;c[nm]=(cam.pos[nm]>=f[nm]?Math.ceil(k-0.01):Math.floor(k+0.01))*g;}
  const key=GRID.i+'|'+GRID.mode+'|'+c.join(',')+'|'+(GRID.col||gridDefCol());
  if(!GRID.prog){GRID.prog=compile(VS_GVL,FS_LINE);GRID.buf=gl.createBuffer();GRID.vao=gvLineVAO(GRID.buf,true);gl.bindVertexArray(null);}
  if(key!==GRID.key){
    GRID.key=key;GRID.c=c;GRID.N=N;
    const col=hexRGB(GRID.col||gridDefCol()),R=N*g,step=Math.max(1,Math.round(N/4)),maj=Math.max(64,g*8);
    const L=[];
    const al=(p,base)=>{const d=Math.hypot(p[0]-c[0],p[1]-c[1],p[2]-c[2])/R;return d>=1?0:base*Math.pow(1-d,1.5);};
    for(let ax=0;ax<3;ax++){const a1=(ax+1)%3,a2=(ax+2)%3;if(ax===nm)continue;    // a plane: none across it
      for(let i=-N;i<=N;i++)for(let j=-N;j<=N;j++){
        if(nm>=0&&((a1===nm&&i)||(a2===nm&&j)))continue;                                 // and only in it
        const v1=c[a1]+i*g,v2=c[a2]+j*g;if(Math.hypot(i,j)>N)continue;
        const base=(v1===0&&v2===0)?0.85:(v1%maj===0&&v2%maj===0)?0.55:(v1%maj===0||v2%maj===0)?0.45:0.36;
        for(let k=-N;k<N;k+=step){const p=[0,0,0],q=[0,0,0];p[a1]=q[a1]=v1;p[a2]=q[a2]=v2;
          p[ax]=c[ax]+k*g;q[ax]=c[ax]+Math.min(N,k+step)*g;
          const ap=al(p,base),aq=al(q,base);if(ap<=0.004&&aq<=0.004)continue;
          L.push(p[0],p[1],p[2],q[0],q[1],q[2],col[0],col[1],col[2],ap,q[0],q[1],q[2],p[0],p[1],p[2],col[0],col[1],col[2],aq);}}}
    GRID.n=L.length/10;
    gl.bindBuffer(gl.ARRAY_BUFFER,GRID.buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(L),gl.STATIC_DRAW);}
  if(!GRID.n)return;
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);gl.disable(gl.CULL_FACE);
  gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  // only in front of the map's surfaces: nothing through floors and walls
  gvUniforms(GRID.prog,vp,0.001);gl.bindVertexArray(GRID.vao);gl.drawArrays(gl.LINES,0,GRID.n);gl.bindVertexArray(null);
  gl.disable(gl.BLEND);gl.depthMask(true);
}
// path node i's spawnflags: a new node's or a changed one's as Modify has them, else its
// info_pathnode's in the map (node i is the map's i-th)
function nodeSpawnflags(A,i){
  const kvOf=m=>{for(const[k,v]of m.kv)if(k.toLowerCase()==='spawnflags')return parseInt(v,10)|0;return 0;};
  const n0=A.n0==null?A.n:A.n0;
  if(A.mod&&i>=n0)return A.mod[i-n0]?kvOf(A.mod[i-n0]):0;
  if(A.edits&&A.edits.has(i))return kvOf(A.edits.get(i));
  const pn=pnEnts();return pn.length===n0&&pn[i]!=null?parseInt(MAP.ents[pn[i]].kvl.spawnflags||'0',10)|0:0;
}
// A node whose spawnflags make the AI face its way (CORNER_LEFT 16, CORNER_RIGHT 32, CRATE
// 128, LOW_WALL_ARC 256: their special attacks, PathNode::GetSpecialAttack, take the
// node's yaw for the way the man turns and the arc he fires in; actor_cover.cpp turns him
// to it) but that has no "angle" or "angles": it faces yaw 0, east, whatever the wall.
// The names of those flags, else ''.
const NODE_FACES=[[16,'CORNER_LEFT'],[32,'CORNER_RIGHT'],[128,'CRATE'],[256,'LOW_WALL_ARC']];
function nodeNoAngle(A,i){
  const sf=nodeSpawnflags(A,i);if(!(sf&(16|32|128|256)))return '';
  const n0=A.n0==null?A.n:A.n0;let k=null;
  if(A.mod&&i>=n0){const m=A.mod[i-n0];if(!m)return '';k=simKvl(m);}
  else if(A.edits&&A.edits.has(i))k=simKvl(A.edits.get(i));
  else{const pn=pnEnts();if(pn.length!==n0||pn[i]==null)return '';k=MAP.ents[pn[i]].kvl;}
  if(k.angle!=null&&String(k.angle).trim()!==''||k.angles!=null&&String(k.angles).trim()!=='')return '';
  return NODE_FACES.filter(x=>sf&x[0]).map(x=>x[1]).join(' + ');
}
// the earlier node on the very spot of node i, once both are dropped to the floor (the one
// the game links: PathSearch::LoadNodes checks the nodes before it), or -1
function nodeDupOf(A,i){
  const x=A.o[i*3],y=A.o[i*3+1],z=A.o[i*3+2];
  for(let j=i-1;j>=0;j--)if(A.o[j*3]===x&&A.o[j*3+1]===y&&A.o[j*3+2]===z)return j;
  return -1;
}
// a path node as a tag names it: its map entity ("entity 111 $friendlynode"), else "new node"
function nodeName(A,j){
  const n0=A.n0==null?A.n:A.n0,pn=pnEnts();
  if(j>=n0)return 'a new node';
  const ei=pn.length===n0?pn[j]:-1;if(ei<0)return 'node '+j;
  const tn=MAP.ents[ei].kvl.targetname;return 'entity '+ei+(tn?' $'+tn:'');
}
// A tag over each path node with something to say. Modify's problems with its new and
// changed nodes (paIssues), wherever they are; and while ai_showroutes draws the routes,
// what its marks mean for every node, the map's and new ones, within
// ai_showroutes_distance (past 350 units only in sight, as the labels): "no paths" (the
// red X: no connection the AI can take), "N one-way" (red arrowheads: it can go but not
// come back, a drop past ai_fallheight back up), "DONT_LINK" (the blue circle: its
// spawnflag keeps it unlinked, on purpose). One tag a node, over its label.
// AI errors (the button by AI routes): its "no paths", "one-way", "own group" and "in the
// wall" tags. It follows AI routes (setCvar), and can be turned off while AI routes is on.
let AIERR=false;
let TRACEPATH=false;     // Trace path (Simulate's actor): his path in blue and red. Turns on and off with AI routes, and can be turned off by itself
const AIERR_KINDS={none:1,island:1,wall:1};
function drawPathIssues2D(){
  const R=PA_ISS,useR=!!(R&&(R.n||R.info)&&MOD.ents.length&&R.A===PA_C);
  const RT=CVARS.ai_showroutes&&ROUTES&&ROUTES.tags&&ROUTES.A===PA_C?ROUTES:null;
  if(!useR&&!(RT&&RT.tags.size))return;
  const A=useR?R.A:RT.A,lbl={links:'48 paths: full',none:'no paths',island:'own group',cell:'cell full: Node overflow',wall:'in the wall'};
  const out=new Map();          // node -> [texts], worst colour
  const add=(i,t,lv)=>{let o=out.get(i);if(!o){o={t:[],lv:0};out.set(i,o);}if(!o.t.includes(t))o.t.push(t);o.lv=Math.max(o.lv,lv);};
  if(useR)for(const[i,l]of R.node)for(const x of l){if(!AIERR&&AIERR_KINDS[x.k])continue;add(i,x.lbl||lbl[x.k],x.lv==null?2:x.lv);}
  if(RT){const far=CVARS.ai_showroutes_distance;
    for(const[i,t]of RT.tags){const p=[A.o[i*3],A.o[i*3+1],A.o[i*3+2]+40];
      const d=Math.hypot(p[0]-cam.pos[0],p[1]-cam.pos[1],p[2]-cam.pos[2]);
      if(d>far||(d>350&&!lblSeen('r'+i,p)))continue;
      if(t.none&&AIERR)add(i,'no paths',2);
      if(t.ow&&AIERR)add(i,t.ow+' one-way',1);
      // DONT_LINK from its own spawnflag is on purpose; without it the game set it while
      // loading: dropped to the floor, the node lands on the very spot of an earlier one
      // ("^~^~^ Duplicate node at (...) not linked", PathSearch::LoadNodes)
      if(t.dl){if(nodeSpawnflags(A,i)&1)add(i,'\u2298 DONT_LINK',0);
        else{if(t.dup===undefined)t.dup=nodeDupOf(A,i);
          add(i,'duplicate of '+(t.dup>=0?nodeName(A,t.dup):'another node')+': not linked',2);}}}
    // the 48-path limit: always, like Modify's own (kind "links")
    for(const[i]of paOver().over){if(i>=A.n||pnGone(A,i))continue;
      const p=[A.o[i*3],A.o[i*3+1],A.o[i*3+2]+40],d=Math.hypot(p[0]-cam.pos[0],p[1]-cam.pos[1],p[2]-cam.pos[2]);
      if(d>far||(d>350&&!lblSeen('r'+i,p)))continue;
      add(i,'48 paths: full',2);}
    if(AIERR)for(let i=0;i<A.n;i++){const p=[A.o[i*3],A.o[i*3+1],A.o[i*3+2]+40];
      const d=Math.hypot(p[0]-cam.pos[0],p[1]-cam.pos[1],p[2]-cam.pos[2]);
      if(d>far||(d>350&&!lblSeen('r'+i,p)))continue;
      const na=nodeNoAngle(A,i);if(na)add(i,'no angle: '+na,2);
      if(A.f[i]&1)continue;
      if(nodeWall([A.o[i*3],A.o[i*3+1],A.o[i*3+2]]))add(i,'in the wall',2);}}
  const col=['#6ea8ff','#ff6b5b','#ffb020'];
  // a node's tag goes just under its class label (on its entity, where the label is
  // whether or not it is drawn; a new node's on Modify's entity), else 40 units over its spot
  const pn=pnEnts(),nMap=A.n0==null?A.n:A.n0,mapEi=pn.length===nMap?pn:null;
  ctx.font='bold 11px ui-monospace,Menlo,Consolas,monospace';ctx.textBaseline='middle';
  for(const[i,o]of out){
    let s;const ei=mapEi&&i<nMap?mapEi[i]:-1,X=ei>=0?ENTS[ei]:null;
    const em=A.edits&&i<nMap?A.edits.get(i):null;          // a map node moved in Modify: its tag goes with it
    const mm=em||(!X&&A.mod&&i>=nMap?A.mod[i-nMap]:null);
    let wp,below=true;
    if(X&&X.anchor&&!em)wp=[X.anchor[0],X.anchor[1],X.anchor[2]+(X.box?X.box.maxs[2]+6:0)];
    else if(mm){const o=modOrigin(mm),b=modBox(mm);wp=[o[0],o[1],o[2]+b.maxs[2]+6];}
    else{wp=[A.o[i*3],A.o[i*3+1],A.o[i*3+2]+40];below=false;}
    if(!view.xray&&!lblSeen('t'+i,wp))continue;           // X-ray off: no tag through a wall
    s=project(wp);if(s&&below)s=[s[0],s[1]+7];
    if(!s||s[0]<0||s[0]>W||s[1]<0||s[1]>H)continue;
    const txt=(o.lv?'\u26a0 ':'')+o.t.join(', '),tw=ctx.measureText(txt).width;
    ctx.fillStyle='rgba('+TH.labelbg+',.85)';ctx.fillRect(s[0]-tw/2-4,s[1]-8,tw+8,16);ctx.fillStyle=col[o.lv];ctx.fillText(txt,s[0]-tw/2,s[1]);}
}
// the coordinates along the three lines through the grid's centre
function drawGrid2D(){
  if(!GRID.on||!GRID.c)return;
  const g=gridSize(),N=GRID.N,c=GRID.c,step=Math.max(1,Math.round(N/4)),R=N*g;
  ctx.font='10px ui-monospace,Menlo,Consolas,monospace';ctx.textBaseline='middle';ctx.fillStyle=GRID.col||gridDefCol();
  const vk=GRID.key+'|'+cam.pos.map(v=>Math.round(v)).join(',');if(GRID.vk!==vk){GRID.vk=vk;GRID.vis.clear();}
  const nm=['x','y','z'];
  const sc=project(c);
  if(sc&&sc[0]>=0&&sc[0]<=W&&sc[1]>=0&&sc[1]<=H&&gridSees(c)){ctx.globalAlpha=0.9;ctx.fillText('( '+c.map(fnum).join(' ')+' )',sc[0]+3,sc[1]+8);}
  const nrm=gridNormal();
  for(let ax=0;ax<3;ax++)for(let k=-N;k<=N;k+=step){if(!k||ax===nrm)continue;
    const p=c.slice();p[ax]=c[ax]+k*g;const sp=project(p);if(!sp||sp[0]<0||sp[0]>W||sp[1]<0||sp[1]>H||!gridSees(p))continue;
    ctx.globalAlpha=0.85*Math.max(0.15,1-Math.abs(k*g)/R);
    ctx.fillText(nm[ax]+' '+fnum(p[ax]),sp[0]+3,sp[1]-6);}
  ctx.globalAlpha=1;
}

// ---- keyboard shortcuts window (H) ---------------------------------------------------
// The keyboard map (kxBuild, KEYS_JS in mohaa_view.py) is built the first time it opens.
// While it is open it takes the keys itself: a key pressed there is looked up, not acted
// on, and Esc or H closes it.
const helpOv=$('helpOv');
let KX=null;
function toggleHelp(force){const show=(force!==undefined)?force:(helpOv.style.display==='none');
  if(show&&!KX){
    try{KX=kxBuild($('helpCard'),JSON.parse($('mohaa-keys').textContent),{onClose:()=>toggleHelp(false)});}
    catch(e){$('helpCard').textContent='The keyboard shortcuts could not be shown: '+e;}}
  helpOv.style.display=show?'flex':'none';
  if(show){legOv.style.display='none';stopCamera();}
  if(KX){if(show)KX.show(camMode==='rad'?'rad':'free');else KX.hide();}}
$('bHelp').onclick=()=>toggleHelp();
helpOv.addEventListener('click',e=>{if(e.target===helpOv)toggleHelp(false);});
function closeViewer(force){
  // MODIFY's new or changed entities not saved: the launcher asks first (Save as .bsp,
  // Save as .map, Discard changes, Cancel); a browser asks with its own box
  const un=!force&&typeof modUnsaved==='function'?modUnsaved():null;
  // In the launcher's pane the host returns to its start page; in a browser tab, just close.
  try{if(window.chrome&&window.chrome.webview){
    if(un){window.chrome.webview.postMessage('mohaa-close-ask\n'+JSON.stringify({new:un.nw,changed:un.ch,isBsp:D.kind==='bsp',name:D.name||''}));return;}
    window.chrome.webview.postMessage('mohaa-close');return;}}catch(_e){}
  if(un&&!window.confirm('MODIFY has '+un.nw+' new and '+un.ch+' changed entities that are not saved. Close anyway and lose them?'))return;
  try{window.close();}catch(_e){}
}

// ---- loading screen ------------------------------------------------------------------
function setLoad(msg,frac){$('loadMsg').textContent=msg;if(frac!=null)$('loadBar').style.width=Math.round(frac*100)+'%';}
function failLoad(msg){const el=$('loading');el.style.display='flex';el.innerHTML='<div class="err">'+esc(msg)+'</div>';}
const tick=()=>new Promise(r=>setTimeout(r,0));

// ============================================================================
//  Page data: "MMV1", JSON header, then binary blobs, all gzipped (see the build)
// ============================================================================
async function loadData(){
  const b64=$('mapdata').textContent.trim();
  if(!b64)throw new Error('This page has no map data.');
  return decodePacket(b64);
}
// a packet in that form (the page's own data, or a model built later for Simulate)
async function decodePacket(b64){
  const bin=atob(b64), n=bin.length, u8=new Uint8Array(n);
  for(let i=0;i<n;i++)u8[i]=bin.charCodeAt(i);
  if(typeof DecompressionStream!=='function')throw new Error('This browser is too old to open the page (no DecompressionStream). Use a current Edge, Chrome or Firefox.');
  const buf=await new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  const dv=new DataView(buf);
  if(String.fromCharCode(dv.getUint8(0),dv.getUint8(1),dv.getUint8(2),dv.getUint8(3))!=='MMV1')throw new Error('Unknown map data format.');
  const hl=dv.getUint32(4,true);
  const hdr=JSON.parse(new TextDecoder('utf-8').decode(new Uint8Array(buf,8,hl)));
  const base=8+hl+((4-((8+hl)%4))%4);
  hdr.bytes=i=>{const b=hdr.blobs[i];return new Uint8Array(buf,base+b[0],b[1]);};
  hdr.f32=i=>{const b=hdr.blobs[i];return new Float32Array(buf,base+b[0],b[1]>>2);};
  hdr.u32=i=>{const b=hdr.blobs[i];return new Uint32Array(buf,base+b[0],b[1]>>2);};
  hdr.i32=i=>{const b=hdr.blobs[i];return new Int32Array(buf,base+b[0],b[1]>>2);};
  hdr.i8=i=>{const b=hdr.blobs[i];return new Int8Array(buf,base+b[0],b[1]);};
  // normals sent as signed bytes x127
  hdr.nrm=i=>{const s=hdr.i8(i),out=new Float32Array(s.length);for(let k=0;k<s.length;k++)out[k]=s[k]/127;return out;};
  return hdr;
}

// ============================================================================
//  State shared by everything below
// ============================================================================
let D=null;          // page data header
let MAP=null;        // parsed .map
let SC=null;         // built geometry (buildScene)
let TEX=[];          // texture entries (build's list plus stand-ins)
const TEXI=new Map();
let ENTS=[];         // per entity: {anchor, origin, box, cat, marker, model, name...}
let NF=0;            // number of pickable faces (ids 1..NF); entity markers use NF+1+entity
const glcv=$('gl'), cv2=$('c'), ctx=cv2.getContext('2d');
let gl=null;
let W=1,H=1,DPR=Math.min(2,window.devicePixelRatio||1);
const view={tex:true,shade:true,wire:false,ss:false,arrows:true,labels:true,links:true,fog:false,xray:true,decals:true,leak:true};
let hiddenMask=C_HINT|C_PORTAL|C_RAIN;
const hidEnt=new Set(), hidPrim=new Set();
const SEL=new Set();            // 'e<entity>' (whole entity) or 'p<primitive>' (one world brush/patch/terrain)
let lastHit=null;               // the last thing clicked: {id, face, ent, prim, point}
let hoverId=0;
const cam={pos:[0,0,0],yaw:0,pitch:0,roll:0};
let camMode='free', moveSpeed=500, fovX=90, clipOn=false, clipDist=4096;
// Full Brightness on: MOHRadiant's look (textures at full brightness with its face
// shading). Off: the game's own lighting, when the page has it (a .bsp; see LIT).
let fullBright=false, LIT=null;
function litOn(){return !!LIT&&!fullBright;}
// Simple Sky on: the sky brushes solid, their picture tiled, as MOHRadiant draws them. Off:
// the game's sky box behind everything (drawGameSky).
let simpleSky=false;
// Simple models on: a tree that has a sprite version (its long-range stand-in, TF_LOD) is
// drawn as that sprite alone, the way the game draws it far away. Off: the whole tree, with
// the sprite left out (the game fades it in only as the tree fades out). See surfOn.
let simpleModels=false;
// Sun flare on: the game's lens flare and glare when the view looks toward the map's sun
// (drawSunFlare). On at first; the In-game look turns it on, the Editor look off.
let sunFlare=true;

function texKey(name){let k=String(name||'').toLowerCase().replace(/\\/g,'/');if(!k.startsWith('textures/'))k='textures/'+k;return k;}
function hashCol(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}
  return[0.35+((h&255)/255)*0.45,0.35+((h>>8&255)/255)*0.45,0.35+((h>>16&255)/255)*0.45];}
// Editor groups for textures the build had no shader for (e.g. no paks loaded).
function guessGroup(k){const m=/^textures\/common\/(.+)$/.exec(k);if(!m)return '';const b=m[1];
  if(/caulk|sunblock/.test(b))return 'caulk';if(/clip$|^clip|^monster$|^weapon$/.test(b))return 'clip';
  if(b==='trigger')return 'trigger';if(b==='origin')return 'origin';if(/^(hint|vis)$/.test(b))return 'hint';
  if(/skip/.test(b))return 'skip';if(/portal/.test(b))return 'portal';if(/nodraw|patharea|rain/.test(b))return 'nodraw';
  if(b==='ladder')return 'ladder';return '';}
function texFor(name){
  const k=texKey(name);let e=TEXI.get(k);
  if(!e){e={n:k,w:64,h:64,f:TF_MISSING,c:hashCol(k),i:TEX.length,standin:1};e.g=guessGroup(k);
    if(e.g&&e.g!=='caulk')e.f|=TF_NODRAW;TEX.push(e);TEXI.set(k,e);}
  return e;
}
// How each texture is drawn: kind 0 solid, 1 alpha-tested, 2 alpha-blended, 3 additive,
// 4 see-through editor surface (clips, triggers...), 5 multiplied (decals).
const EDITOR_SEE_THROUGH={clip:1,trigger:1,hint:1,skip:1,portal:1,origin:1,nodraw:1,ladder:1,fog:1};
function matOf(te){
  const m={kind:0,af:0,alpha:1};
  const af={gt0:1,ge128:2,lt128:3}[te.at||''];
  if(te.f&TF_ADD)m.kind=3;
  else if(te.f&TF_BLEND)m.kind=2;
  else if(te.f&TF_FILTER)m.kind=5;
  else if((te.f&TF_ALPHATEST)&&af){m.kind=1;m.af=af;}
  if(m.kind===0&&(EDITOR_SEE_THROUGH[te.g]||(te.f&TF_NODRAW&&!(te.f&TF_SKY)&&te.g!=='caulk'))){
    m.alpha=(te.a!=null)?te.a:0.45;if(m.alpha<0.99)m.kind=4;}
  if(te.g==='liquid'&&m.kind===0){m.kind=4;m.alpha=te.a!=null?te.a:0.6;}
  // a sky face is solid, its picture tiled, as MOHRadiant draws it (Simple Sky); the
  // game's sky is drawn apart from the faces (drawGameSky)
  if(te.f&TF_SKY){m.kind=0;m.af=0;m.alpha=1;}
  if(te.f&TF_ALPHATEST&&af)m.af=af;
  // See-through editor surfaces are drawn one-sided, as MOHRadiant does: the near side of
  // a hint or clip brush hides nothing, and its far side isn't drawn through it.
  m.two=!!(te.f&TF_TWOSIDED);
  // the editor's own see-through volumes (triggers, clips, hints, fog...): drawn after
  // the game's see-through surfaces, so water never paints over a trigger above it
  m.ed=m.kind===4&&te.g!=='liquid';
  // With the game's lighting a surface is drawn the way its picture's stage draws it in
  // game: water solid unless its shader blends, with the stage's texture scale and
  // alphaGen, and writing depth when a blended stage says depthWrite.
  const g=Object.assign({},m,{ed:false,tm:te.tm||null,dw:!!te.dw,agk:0,agp:[1,0,0,1]});
  if(te.g==='liquid'&&g.kind===4){g.kind=0;g.alpha=1;}
  const ag=te.ag;
  if(ag){if(ag[0]==='c'){g.agk=1;g.agp=[ag[1],0,0,1];}
    else if(ag[0]==='s'||ag[0]==='t'){g.agk=ag[0]==='s'?2:3;g.agp=[ag[1],ag[2],ag[3],ag[4]];}
    else if(ag[0]==='v')g.agk=4;else if(ag[0]==='1v')g.agk=5;}
  m.lit=g;
  return m;
}

// ============================================================================
//  Entities: anchors, boxes, markers
// ============================================================================
function entName(ei){const e=MAP.ents[ei];const tn=e.kvl.targetname;return (e.kvl.classname||'?')+(tn?' $'+tn:'');}
function buildEntities(){
  ENTS=[];
  const tnIndex=new Map();
  for(let ei=0;ei<MAP.ents.length;ei++){
    const e=MAP.ents[ei], inf=SC.entInfo[ei];
    const o=parseVec(e.kvl.origin,3);
    const hasGeo=isFinite(inf.mins[0]);
    const def=(D.defs||{})[e.cls]||null;
    const X={ei:ei,origin:o,hasGeo:hasGeo,def:def,cat:0,marker:0,model:-1,anchor:null,box:null,col:def?def.c:[0.6,0.6,0.6]};
    if(hasGeo)X.anchor=o||[(inf.mins[0]+inf.maxs[0])/2,(inf.mins[1]+inf.maxs[1])/2,(inf.mins[2]+inf.maxs[2])/2];
    else X.anchor=o;
    if(ei>0&&!WORLDLIKE[e.cls]&&!hasGeo&&o){
      const mi=(D.modelOf||{})[ei];
      if(mi!=null&&D.models[mi]){X.model=mi;X.cat=C_MODEL|(isStaticProp(ei)?C_STATIC:0);}
      else{
        X.marker=(e.cls==='light'||e.cls.startsWith('light_'))?2:1;
        if(X.marker===2)X.cat=C_LIGHT;
        else if(e.cls==='info_pathnode'||e.cls.startsWith('info_pathnode'))X.cat=C_AINODE;
        else if(/^info_(spline|waypoint|vehiclepoint)|path/.test(e.cls))X.cat=C_PATH;
        else X.cat=C_POINT;
        if(X.marker===2){const lc=parseVec(e.kvl._color||e.kvl.color,3);if(lc){const mx=Math.max(lc[0],lc[1],lc[2],1e-6);X.col=lc.map(v=>Math.max(0.15,v/mx));}else X.col=[1,0.92,0.6];}
        else radiantLook(X,e);
      }
    }
    if(hasGeo&&ei>0&&!WORLDLIKE[e.cls])X.cat|=C_ENTBRUSH;
    if(e.scr){X.cat|=C_SCRIPT;X.scr=true;}
    const tn=e.kvl.targetname;if(tn){let l=tnIndex.get(tn);if(!l){l=[];tnIndex.set(tn,l);}l.push(ei);}
    ENTS.push(X);
  }
  ENTS.tn=tnIndex;
  for(const X of ENTS){const b=entityBox(X.ei);X.box=b&&!b.wmins?boxWorld(b):b;
    // a trigger the level script spawns with a setsize: its marker keeps the class's small
    // box (Script ents), and the setsize is drawn as its volume (Script trigs)
    X.mbox=X.box;
    const e=MAP.ents[X.ei];
    if(X.ei>0&&e.scr&&X.marker&&X.box&&parseVec(e.kvl.setsize,6)&&(GAME_CLASS[e.cls]==='trigger'||e.cls.startsWith('trigger'))){
      X.scrTrig=true;X.mbox=markerBoxOf(X);}}
}
// MOHRadiant's camera colours a point entity's box like this (its brush drawing, read from
// mohradiant.exe): an info_path... class with a "targetname" gets its class colour turned
// inside out (1 - colour, so a green node turns pink); otherwise a "_color" key paints the
// box flat in that colour; otherwise it is the class colour, each side shaded by the way
// it faces.
// MOHRadiant reads class definitions from the .tik files and from its entity folder
// (code/) on disk; the game code's ship inside entdefs.pk3, so it reports every game-code
// class as "Not found in source." and draws it as its stand-in: dark green, a 16-unit
// cube on the origin. Player starts, path nodes, script origins and the rest look like
// that there, so here too; classes defined in a .tik keep their definition.
const RAD_STANDIN_COL=[0,0.5,0];
function radiantKnows(def){return !!(def&&def.s&&/\.tik$/i.test(def.s));}
// A key's first value as written in the .map, as the editor reads it (no "$" or "#" forms).
function edKey(e,name){for(const[k,v]of e.kv)if(k.toLowerCase()===name)return v;return '';}
function radiantLook(X,e){
  X.standin=!radiantKnows(X.def);
  if(X.standin)X.col=RAD_STANDIN_COL.slice();
  X.ccol=X.col;X.mcol=X.col;X.mk=1;
  const lc=parseVec(e.kvl._color,3);
  // the key as written: to MOHRadiant "$targetname" is any other key (kvl takes it as the game does)
  if(e.cls.startsWith('info_path')&&edKey(e,'targetname')){X.mk=2;X.col=X.ccol.map(v=>1-v);X.why='it has a "targetname"';}
  else if(lc){X.mk=0;X.col=X.mcol=lc.map(v=>Math.min(1,Math.max(0,v)));X.why='its "_color" key';}
  X.ol=e.cls==='info_pathnode'?nodeOutline(parseInt(e.kvl.spawnflags||'0',10)|0):null;
}
// The thick outline MOHRadiant draws round a path node, by its spawnflags (5 pixels wide,
// checked in this order; the game's ai_editmode uses the same colours, navigate.cpp).
// Black: flags the AI can't combine (IsValidPathnode). None: a plain node.
const NODE_OUTLINES=[[4,[0,1,0],'COVER'],[16,[1,1,0],'CORNER_LEFT'],[32,[0.7,1,0],'CORNER_RIGHT'],[64,[1,0,0],'SNIPER'],
  [128,[0.5,0,0],'CRATE'],[8,[0,0,1],'CONCEALMENT'],[2,[0,1,1],'DUCK']];
function nodeFlagsBad(sf){
  const v=sf&0xfe;
  return !!(((v&2)&&(v&~0x06))||((v&8)&&(v&~0x8a))||((v&16)&&(v&~0x14))||((v&32)&&(v&~0x24))||((v&64)&&(v&~0x40))||((v&128)&&(v&~0x84)));
}
function nodeOutline(sf){
  if(nodeFlagsBad(sf))return [0,0,0];
  for(const[b,c]of NODE_OUTLINES)if(sf&b)return c;
  return null;
}
// Whether the game turns a model entity's box with its angles (EF_LINKANGLES: the box's
// trace, CM_TransformedBoxTrace, then rotates by r.currentAngles, and SV_LinkEntity links
// the turned box's bounds). ScriptSlave sets it (script_model, script_object and the rest
// of the 'slave' group), so do Vehicle and VehicleCollisionEntity; "rotatedbbox" sets or
// clears it (Entity::EventSetRotatedBbox), as a map key or a script line. Other classes
// (an Actor, an Animate...) keep an unturned box whatever their angles.
function boxTurns(ei){
  const e=MAP.ents[ei],rb=e.kvl.rotatedbbox;
  if(rb!=null&&rb!=='')return (parseInt(rb,10)|0)!==0;
  const M=ENTS[ei]&&ENTS[ei].model>=0?D.models[ENTS[ei].model]:null;
  let g=GAME_CLASS[e.cls];
  if(!g&&M&&M.cn)g=GAME_CLASS[String(M.cn).toLowerCase()];
  return g==='slave'||g==='vehicle'||e.cls==='vehiclecollisionentity';
}
// A box's eight corners in the world (corner k: bit 1 x, 2 y, 4 z at the max end, as
// boxLines), turned by its axes (B.ax: forward, left, up) when it has them; origin o in
// place of its own (a moved door's).
function boxCorners(B,o){
  o=o||B.origin;const a=B.ax,C=[];
  for(let k=0;k<8;k++){const t=[(k&1)?B.maxs[0]:B.mins[0],(k&2)?B.maxs[1]:B.mins[1],(k&4)?B.maxs[2]:B.mins[2]];
    C.push(a?[o[0]+t[0]*a[0][0]+t[1]*a[1][0]+t[2]*a[2][0],o[1]+t[0]*a[0][1]+t[1]*a[1][1]+t[2]*a[2][1],o[2]+t[0]*a[0][2]+t[1]*a[1][2]+t[2]*a[2][2]]
      :[o[0]+t[0],o[1]+t[1],o[2]+t[2]]);}
  return C;
}
// B.wmins / B.wmaxs: the box's bounds along the world's axes, from its origin (the turned
// box's, as CalculateRotatedBounds2 gives SV_LinkEntity's absmin / absmax)
function boxWorld(B){
  if(!B.ax){B.wmins=B.mins;B.wmaxs=B.maxs;return B;}
  const C=boxCorners(B,[0,0,0]),mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  for(const c of C)for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],c[k]);mx[k]=Math.max(mx[k],c[k]);}
  B.wmins=mn;B.wmaxs=mx;return B;
}
// the box a marker is drawn with when its setsize is shown otherwise: MOHRadiant's 16-unit
// stand-in, else the class's editor box (as entityBox without the setsize)
function markerBoxOf(X){
  const B=X.standin||!(X.def&&X.def.b)?{origin:X.origin,mins:[-8,-8,-8],maxs:[8,8,8]}:{origin:X.origin,mins:X.def.b[0],maxs:X.def.b[1]};
  return boxWorld(B);
}
// The entity's box as the game sees it: origin plus setsize mins/maxs, and where it
// comes from. Brush entities: a .bsp gives the exact box; a .map is worked out the way
// the compiler does it (origin brush centre, else the "origin" key, else the middle of
// the brushes). Point entities: the model's .tik setsize, else its size, else the
// class's editor box.
function entityBox(ei){
  const e=MAP.ents[ei], X=ENTS[ei], inf=SC.entInfo[ei];
  if(ei===0)return null;
  const o=X.origin;
  if(X.hasGeo){
    const bb=D.bsp&&D.bsp.bounds&&D.bsp.bounds[ei];
    if(bb&&o)return{origin:o,mins:bb[0],maxs:bb[1],how:'exact (from the compiled .bsp)',exact:true};
    let org=null,how='';
    if(inf.originBrush){org=inf.originBrush;how='origin brush centre (exact)';}
    else if(o){org=o;how='"origin" key';}
    else{org=[(inf.mins[0]+inf.maxs[0])/2,(inf.mins[1]+inf.maxs[1])/2,(inf.mins[2]+inf.maxs[2])/2];how='the middle of its brushes, where the compiler puts its origin';}
    return{origin:org,mins:[inf.mins[0]-org[0],inf.mins[1]-org[1],inf.mins[2]-org[2]],maxs:[inf.maxs[0]-org[0],inf.maxs[1]-org[1],inf.maxs[2]-org[2]],how:how,exact:!!inf.originBrush};
  }
  if(!o)return null;
  // A model's setsize box turns with its angles when the game turns it (boxTurns); its own
  // size always does, being the model's.
  const ang=entAngles(e.kvl),turned=ang[0]||ang[1]||ang[2], ax=turned?anglesAxis(ang):null;
  const set=(B)=>{if(ax&&X.model>=0&&boxTurns(ei)){B.ax=ax;B.how+=', turned with its angles';}
    else if(ax&&X.model>=0&&B.exact)B.how+=(e.kvl.rotatedbbox!=null&&e.kvl.rotatedbbox!==''?'; "rotatedbbox" 0: the game doesn\'t turn its box with its angles'
      :'; the game doesn\'t turn this class\'s box with its angles');
    return boxWorld(B);};
  const ss=parseVec(e.kvl.setsize,6);
  if(ss)return set({origin:o,mins:ss.slice(0,3),maxs:ss.slice(3),how:'"setsize" key',exact:true});
  if(X.model>=0){const M=D.models[X.model];const sc=parseFloat(e.kvl.scale)||1;
    if(M.ss)return set({origin:o,mins:M.ss[0],maxs:M.ss[1],how:'setsize in '+M.p.replace(/^models\//,''),exact:true});
    // the model's own size, turned with the entity
    return boxWorld({origin:o,mins:M.b[0].map(v=>v*sc),maxs:M.b[1].map(v=>v*sc),ax:ax,how:'model size (no setsize in its .tik), turned with the model',exact:false});}
  if(X.standin)return{origin:o,mins:[-8,-8,-8],maxs:[8,8,8],exact:false,
    how:'MOHRadiant\'s stand-in for a class it has no definition for, a 16-unit cube on the origin'+(e.cls==='info_pathnode'?' (a path node has no size in game)':'')};
  const d=X.def;
  if(d&&d.b)return{origin:o,mins:d.b[0],maxs:d.b[1],how:'editor box of the class',exact:false};
  return{origin:o,mins:[-8,-8,-8],maxs:[8,8,8],how:'no size known (16-unit marker)',exact:false};
}

// ============================================================================
//  WebGL
// ============================================================================
// uPush moves a face away from the camera along each vertex's own line of sight (so it
// covers the same pixels, only further back): caulk gets half a unit, so it can't win
// the depth test against a wall it touches.
const VS_WORLD=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV; layout(location=2) in float aPick;
uniform mat4 uVP; uniform vec3 uEye; uniform float uPush;
out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
void main(){vUV=aUV;vPos=aPos;vCol=vec4(1.0);vPick=aPick;
  vec3 p=aPos; if(uPush>0.0){vec3 d=aPos-uEye;p+=d*(uPush/max(length(d),1.0));}
  gl_Position=uVP*vec4(p,1.0);}`;
// Models. With the game's lighting on (uLit), a static prop takes its baked vertex light
// from uStatic (one texel per engine vertex, from the instance's first one in aILight.w);
// other models take the light grid's colour for their position (aILight.rgb).
// uAuto2 draws a tree's sprite version the way deformVertexes autoSprite2 does
// (tr_shade_calc.c Autosprite2Deform): each quad turns about its long axis to face the
// camera's forward direction (uFwd), so a tree's sprite stays upright. aA2 is the middle of
// the vertex's end of the quad and half that end's length, signed for its side; aA2M the
// quad's long axis (see auto2Data).
const VS_MODEL=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV;
layout(location=3) in vec4 aR0; layout(location=4) in vec4 aR1; layout(location=5) in vec4 aR2; layout(location=6) in float aIPick;
layout(location=9) in float aEng; layout(location=10) in vec4 aILight;
layout(location=11) in vec4 aA2; layout(location=12) in vec3 aA2M; layout(location=15) in float aISlot;
layout(location=13) in float aIStatic; layout(location=14) in vec3 aNrm;
uniform mat4 uVP; uniform int uLit; uniform highp sampler2D uStatic; uniform int uAuto2; uniform vec3 uFwd; uniform int uRel;
uniform vec4 uDv; uniform vec4 uDw; uniform int uDf; uniform float uTime; uniform vec4 uMul;
out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
// the engine's wave tables (tr_init.c): sin, triangle, square, sawtooth, inverse sawtooth
float wf(int f,float x){x=fract(x);
  if(f==1)return x<0.25?4.0*x:x<0.75?2.0-4.0*x:4.0*x-4.0;
  if(f==2)return x<0.5?1.0:-1.0; if(f==3)return x; if(f==4)return 1.0-x;
  return sin(x*6.28318530718);}
void main(){vec4 p=vec4(aPos,1.0);
  // deformVertexes wave / flap (tr_shade_calc.c RB_CalcDeformVertexes, RB_CalcFlapVertexes):
  // along the vertex's normal by base + amplitude x wave(phase + time x frequency), a wave
  // shifted by (x + y + z) / spread, a flap scaled by min .. max along s or t. A static
  // model's four are scaled by r_static_shadermultiplier0 .. 3 (it has no entity)
  if(uDv.x>0.5&&uAuto2==0){vec4 q=uDw;if(aIStatic>0.5)q*=uMul;
    float sc;
    if(uDv.x<1.5){float off=(p.x+p.y+p.z)*uDv.y;sc=q.w==0.0?q.x+wf(uDf,q.z)*q.y:q.x+wf(uDf,q.z+off+uTime*q.w)*q.y;}
    else{sc=(q.x+wf(uDf,q.z+uTime*q.w)*q.y)*((uDv.w-uDv.z)*(uDv.x<2.5?aUV.x:aUV.y)+uDv.z);}
    p.xyz+=aNrm*sc;}
  vec3 w=vec3(dot(aR0,p),dot(aR1,p),dot(aR2,p));
  if(uAuto2==1){vec4 m=vec4(aA2.xyz,1.0);
    vec3 ax=vec3(dot(aR0.xyz,aA2M),dot(aR1.xyz,aA2M),dot(aR2.xyz,aA2M)), mn=cross(ax,uFwd);
    float l=length(mn), sc=length(vec3(aR0.x,aR1.x,aR2.x));
    w=vec3(dot(aR0,m),dot(aR1,m),dot(aR2,m))+(l>1e-6?mn*(aA2.w*sc/l):vec3(0.0));}
  vec4 c=vec4(1.0);
  if(uLit==2&&aILight.w>=0.0){int k=int(aILight.w+aEng+0.5);c=vec4(texelFetch(uStatic,ivec2(k%4096,k/4096),0).rgb,1.0);}
  else if(uLit>0){c=vec4(aILight.rgb,1.0);
    // with a light turned off, its grid colour relit: its probe in the same texture (LT)
    if(uRel==1&&aISlot>=0.0){int k=int(aISlot+0.5);c=vec4(texelFetch(uStatic,ivec2(k%4096,k/4096),0).rgb,1.0);}}
  vUV=aUV;vPos=w;vCol=c;vPick=aIPick;gl_Position=uVP*vec4(w,1.0);}`;
// The game's own polygons: texture x lightmap page (aLM.z >= 0), x vertex light
// (aLM.z = -1) or as it is (aLM.z = -2); with uLMOnly (r_lightmap) a lightmapped one shows
// its lightmap alone, the texture's alpha still cutting it. uTm is the picture stage's tcMod scale
// (RB_CalcScaleTexCoords); uAg its alphaGen (tr_shade.c ComputeColors): 1 constant,
// 2 / 3 from the base s / t coordinate (RB_CalcAlphaFromTexCoords: min, max, low cap,
// high cap in uAgP), 4 vertex alpha, 5 one minus vertex alpha. aVP is a vertex-lit vertex's
// slot among the lights' probes (-1 for the rest; see LT), read with lights turned off.
const VS_LIT=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV; layout(location=7) in vec4 aCol; layout(location=8) in vec3 aLM;
layout(location=13) in float aVP;
uniform mat4 uVP; uniform vec2 uTm; uniform int uAg; uniform vec4 uAgP;
uniform highp sampler2D uVR; uniform int uVROn;
out vec2 vUV; out vec3 vPos; out vec4 vCol; out vec3 vLM; out float vA;
void main(){vUV=aUV*uTm;vPos=aPos;vCol=aCol;vLM=aLM;
  // with a light turned off, a vertex-lit vertex's light is its relit probe (LT)
  if(uVROn==1&&aVP>=0.0){int k=int(aVP+0.5);vCol=vec4(texelFetch(uVR,ivec2(k%4096,k/4096),0).rgb,aCol.a);}
  float a=1.0;
  if(uAg==1)a=uAgP.x;
  else if(uAg==2||uAg==3){float f=(uAg==2)?aUV.x:aUV.y;a=max(min((uAgP.y-uAgP.x)*f+uAgP.x,uAgP.w),uAgP.z);}
  else if(uAg==4)a=aCol.a;
  else if(uAg==5)a=1.0-aCol.a;
  vA=a;gl_Position=uVP*vec4(aPos,1.0);}`;
const FS_LIT=`#version 300 es
precision highp float;
in vec2 vUV; in vec3 vPos; in vec4 vCol; in vec3 vLM; in float vA;
uniform sampler2D uTex; uniform highp sampler2DArray uLM; uniform int uAF; uniform vec4 uTint;
uniform int uUseTex; uniform vec3 uFlat; uniform vec3 uFogCol; uniform vec3 uFog; uniform vec3 uEye; uniform float uClip;
uniform int uLMOnly;
out vec4 o;
void main(){
  if(uClip>0.0){vec3 d=abs(vPos-uEye);if(max(d.x,max(d.y,d.z))>uClip)discard;}
  vec4 t=(uUseTex==1)?texture(uTex,vUV):vec4(uFlat,1.0);
  if(uAF==1&&t.a<=0.0)discard; if(uAF==2&&t.a<0.5)discard; if(uAF==3&&t.a>=0.5)discard;
  vec3 l=vLM.z>-0.5?texture(uLM,vec3(vLM.xy,floor(vLM.z+0.5))).rgb:(vLM.z>-1.5?vCol.rgb:vec3(1.0));
  vec3 c=(uLMOnly==1&&vLM.z>-0.5)?l*uTint.rgb:t.rgb*l*uTint.rgb;
  if(uFog.z>0.5){float f=clamp((distance(vPos,uEye)-uFog.x)/max(1.0,uFog.y-uFog.x),0.0,1.0);c=mix(c,uFogCol,f);}
  o=vec4(c,t.a*vA*uTint.a);
}`;
// Sky polygons: the shader's sky box seen in the direction of each pixel (tr_sky.c), or
// one flat colour when there is no box. Drawn with the depth range squeezed to the far
// end (RB_StageIteratorSky: qglDepthRange(1, 1)), so the sky is behind everything and
// whatever is behind a sky brush shows through it, as in game. Paired with VS_LIT for a
// .bsp's own sky polygons and with VS_WORLD for a .map's sky faces.
// Then the shader's cloud layers (R_BuildCloudData), each blended over what is there with
// its own blendFunc; skyFS(n) is the program for n of them (0 to 4, compiled when first
// needed, so a sky without clouds costs nothing extra). A layer's texture coordinates come
// from where the pixel's direction meets a sphere 4096 units in radius whose top is the
// cloud height (uCH) above the eye: the arc cosines of that point's x and y
// (R_InitSkyTexCoords), then the stage's tcMods as one affine map (uCA / uCB rows, worked
// out each frame in cloudStage). uCC is its rgbGen x alphaGen colour; uCF its source and
// destination factor (0 zero, 1 one, 2 / 3 (one minus) source colour, 4 / 5 destination
// colour, 6 / 7 source alpha, 8 / 9 destination alpha, which is always 1 here, 10
// saturate) and alphaFunc. The bottom face of the box gets no clouds, as in FillCloudBox.
function skyFS(n){
  let s=`#version 300 es
precision highp float;
in vec3 vPos;
uniform highp sampler2DArray uSky; uniform int uHasBox; uniform vec3 uSkyCol; uniform vec3 uEye; uniform float uClip;
out vec4 o;
`;
  if(n)s+=`uniform float uCH; uniform sampler2D uC0,uC1,uC2,uC3;
uniform vec3 uCA[4]; uniform vec3 uCB[4]; uniform vec4 uCC[4]; uniform ivec3 uCF[4];
vec3 factor(int f,vec4 s,vec3 d){
  if(f==0)return vec3(0.0); if(f==1||f==8)return vec3(1.0); if(f==2)return s.rgb; if(f==3)return 1.0-s.rgb;
  if(f==4)return d; if(f==5)return 1.0-d; if(f==6)return vec3(s.a); if(f==7)return vec3(1.0-s.a);
  return vec3(0.0);}
vec3 cloud(sampler2D tex,vec3 A,vec3 B,vec4 C,ivec3 F,vec2 st,vec3 d){
  vec4 s=texture(tex,vec2(dot(A.xy,st)+A.z,dot(B.xy,st)+B.z))*C;
  if((F.z==1&&s.a<=0.0)||(F.z==2&&s.a<0.5)||(F.z==3&&s.a>=0.5))return d;
  return clamp(s.rgb*factor(F.x,s,d)+d*factor(F.y,s,d),0.0,1.0);}
`;
  s+=`void main(){
  if(uClip>0.0){vec3 d=abs(vPos-uEye);if(max(d.x,max(d.y,d.z))>uClip)discard;}
`;
  if(!n)s+=`  if(uHasBox==0){o=vec4(uSkyCol,1.0);return;}
`;
  s+=`  vec3 v=vPos-uEye, a=abs(v); float s,t,dv; float layer;
  // which face (AddSkyPolygon) and where on it (vec_to_st); faces in rt bk lf ft up dn order
  if(a.x>a.y&&a.x>a.z){
    if(v.x<0.0){dv=-v.x;s=v.y/dv;t=v.z/dv;layer=2.0;}else{dv=v.x;s=-v.y/dv;t=v.z/dv;layer=0.0;}}
  else if(a.y>a.z){
    if(v.y<0.0){dv=-v.y;s=-v.x/dv;t=v.z/dv;layer=3.0;}else{dv=v.y;s=v.x/dv;t=v.z/dv;layer=1.0;}}
  else{
    if(v.z<0.0){dv=-v.z;s=-v.y/dv;t=v.x/dv;layer=5.0;}else{dv=v.z;s=-v.y/dv;t=-v.x/dv;layer=4.0;}}
  vec2 st=vec2((s+1.0)*0.5,(1.0-t)*0.5);
`;
  if(!n)return s+`  o=vec4(texture(uSky,vec3(clamp(st,0.0,1.0),layer)).rgb,1.0);
}`;
  s+=`  vec3 c=uHasBox==1?texture(uSky,vec3(clamp(st,0.0,1.0),layer)).rgb:uSkyCol;
  vec3 d=normalize(v); float R=4096.0;
  float p=-d.z*R+sqrt(d.z*d.z*R*R+2.0*R*uCH+uCH*uCH);
  vec3 q=(d*p+vec3(0.0,0.0,R))/(R+uCH);
  vec2 cs=vec2(acos(clamp(q.x,-1.0,1.0)),acos(clamp(q.y,-1.0,1.0)));
  vec3 k=c;
`;
  for(let i=0;i<n;i++)s+=`  k=cloud(uC${i},uCA[${i}],uCB[${i}],uCC[${i}],uCF[${i}],cs,k);
`;
  return s+`  if(layer!=5.0)c=k;
  o=vec4(c,1.0);
}`;
}
const VS_COL=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=7) in vec4 aCol; layout(location=2) in float aPick;
uniform mat4 uVP;
out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
void main(){vUV=vec2(0.5);vPos=aPos;vCol=aCol;vPick=aPick;gl_Position=uVP*vec4(aPos,1.0);}`;
const FS_MAIN=`#version 300 es
precision highp float;
in vec2 vUV; in vec3 vPos; in vec4 vCol; flat in float vPick;
uniform sampler2D uTex; uniform int uMode; uniform int uAF; uniform float uShade; uniform vec4 uTint;
uniform int uUseTex; uniform vec3 uFlat; uniform vec3 uFogCol; uniform vec3 uFog; uniform vec3 uEye; uniform float uClip;
out vec4 o;
void main(){
  if(uClip>0.0){vec3 d=abs(vPos-uEye);if(max(d.x,max(d.y,d.z))>uClip)discard;}
  vec4 t=(uUseTex==1)?texture(uTex,vUV):vec4(uFlat,1.0);
  t*=vCol;
  if(uAF==1&&t.a<=0.0)discard; if(uAF==2&&t.a<0.5)discard; if(uAF==3&&t.a>=0.5)discard;
  if(uMode==1){float id=vPick;o=vec4(mod(id,256.0),mod(floor(id/256.0),256.0),mod(floor(id/65536.0),256.0),255.0)/255.0;return;}
  if(uMode==2){o=uTint;return;}
  vec3 n=normalize(cross(dFdx(vPos),dFdy(vPos)));
  float sh=mix(1.0,0.9*n.x*n.x+0.8*n.y*n.y+1.0*n.z*n.z,uShade);
  vec3 c=t.rgb*sh*uTint.rgb;
  if(uFog.z>0.5){float f=clamp((distance(vPos,uEye)-uFog.x)/max(1.0,uFog.y-uFog.x),0.0,1.0);c=mix(c,uFogCol,f);}
  o=vec4(c,t.a*uTint.a);
}`;
// Point-entity markers, drawn the way MOHRadiant's camera draws them. aCol.a picks how
// the colour is used: 0 flat (a "_color" key), 1 shaded like MOHRadiant (SetShadeForPlane:
// sides facing x 0.6, y 0.8, up/down 1.0), 2 the same turned inside out (a path node with
// a targetname), 3 a light's diamond. aOl is a path node's outline colour (alpha 0 = none),
// drawn uOlW pixels in from each edge of the box: aBox runs 0..1 across the box, 0.5 on
// the axis a side faces, so the distance to the nearest edge is known in pixels.
const VS_MARK=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=7) in vec4 aCol; layout(location=2) in float aPick;
layout(location=8) in vec3 aBox; layout(location=10) in vec4 aOl;
uniform mat4 uVP;
out vec3 vPos; out vec4 vCol; out vec3 vBox; flat out vec4 vOl; flat out float vPick;
void main(){vPos=aPos;vCol=aCol;vBox=aBox;vOl=aOl;vPick=aPick;gl_Position=uVP*vec4(aPos,1.0);}`;
const FS_MARK=`#version 300 es
precision highp float;
in vec3 vPos; in vec4 vCol; in vec3 vBox; flat in vec4 vOl; flat in float vPick;
uniform int uMode; uniform float uShade; uniform vec3 uFogCol; uniform vec3 uFog; uniform vec3 uEye; uniform float uClip; uniform float uOlW;
out vec4 o;
void main(){
  if(uClip>0.0){vec3 d=abs(vPos-uEye);if(max(d.x,max(d.y,d.z))>uClip)discard;}
  if(uMode==1){float id=vPick;o=vec4(mod(id,256.0),mod(floor(id/256.0),256.0),mod(floor(id/65536.0),256.0),255.0)/255.0;return;}
  vec3 n=normalize(cross(dFdx(vPos),dFdy(vPos)));
  vec3 c=vCol.rgb;
  if(vCol.a>2.5)c*=mix(1.0,0.9,uShade);
  else if(vCol.a>0.5){c*=mix(1.0,0.6*n.x*n.x+0.8*n.y*n.y+n.z*n.z,uShade);if(vCol.a>1.5)c=1.0-c;}
  if(vOl.a>0.5){
    vec3 g=vec3(length(vec2(dFdx(vBox.x),dFdy(vBox.x))),length(vec2(dFdx(vBox.y),dFdy(vBox.y))),length(vec2(dFdx(vBox.z),dFdy(vBox.z))));
    vec3 q=min(vBox,1.0-vBox)/max(g,vec3(1e-6));
    c=mix(vOl.rgb,c,smoothstep(uOlW-0.5,uOlW+0.5,min(q.x,min(q.y,q.z))));
  }
  if(uFog.z>0.5){float f=clamp((distance(vPos,uEye)-uFog.x)/max(1.0,uFog.y-uFog.x),0.0,1.0);c=mix(c,uFogCol,f);}
  o=vec4(c,1.0);
}`;
const VS_LINE=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=7) in vec4 aCol;
uniform mat4 uVP; out vec4 vC;
void main(){vC=aCol;gl_Position=uVP*vec4(aPos,1.0);}`;
const FS_LINE=`#version 300 es
precision mediump float; in vec4 vC; uniform float uAlpha; out vec4 o;
void main(){o=vec4(vC.rgb,vC.a*uAlpha);}`;

let PW=null,PM=null,PC=null,PL=null;   // programs: world, model, coloured, lines
let PMK=null;                          // entity markers
let PLIT=null;                         // the game's lighting: lit polygons
const PSKY={};                         // the game's sky, by polygons (L .bsp, W .map faces) and cloud layers
const GLT=[];                          // GL texture per TEX entry
const GLTG=[];                         // the game's own picture where it differs (water)
let whiteTex=null;
const B={};                            // buffers / vertex arrays
let drawOps=[], drawTrans=[];          // world draw calls (solid / see-through)
let drawTransG=[], drawTransE=[];      // the see-through ones: the game's / the editor's volumes
let selTriCount=0, selEdgeCount=0, hovEdgeCount=0, hovBoxVerts=0, wireCount=0, boxCount=0;
let lineVerts=0, hotVerts=0, lineDirty=true;

function compile(vs,fs){
  const mk=(t,s)=>{const sh=gl.createShader(t);gl.shaderSource(sh,s);gl.compileShader(sh);
    if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw new Error('shader: '+gl.getShaderInfoLog(sh));return sh;};
  const p=gl.createProgram();gl.attachShader(p,mk(gl.VERTEX_SHADER,vs));gl.attachShader(p,mk(gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);
  if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error('program: '+gl.getProgramInfoLog(p));
  p.u={};const n=gl.getProgramParameter(p,gl.ACTIVE_UNIFORMS);
  for(let i=0;i<n;i++){const a=gl.getActiveUniform(p,i);p.u[a.name]=gl.getUniformLocation(p,a.name);}
  return p;
}
// the sky program for this page's sky polygons (a .bsp's own, else the .map's sky faces)
// with n cloud layers
function skyProgram(n){const key=(LIT?'L':'W')+n;
  return PSKY[key]||(PSKY[key]=compile(LIT?VS_LIT:VS_WORLD,skyFS(n)));}
function makeBuf(target,data,usage){const b=gl.createBuffer();gl.bindBuffer(target,b);gl.bufferData(target,data,usage||gl.STATIC_DRAW);return b;}
function attr(loc,buf,size,stride,off,div){gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc,size,gl.FLOAT,false,stride||0,off||0);if(div)gl.vertexAttribDivisor(loc,div);}
function worldVAO(ibo){const v=gl.createVertexArray();gl.bindVertexArray(v);
  attr(0,B.pos,3);attr(1,B.uv,2);attr(2,B.pick,1);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bindVertexArray(null);return v;}

function initGL(){
  gl=glcv.getContext('webgl2',{antialias:true,alpha:false,depth:true,stencil:false,premultipliedAlpha:false});
  if(!gl)throw new Error('WebGL 2 is not available in this browser, and the map viewer needs it.\n(Try a current Edge, Chrome or Firefox, and check that hardware acceleration is on.)');
  PW=compile(VS_WORLD,FS_MAIN);PM=compile(VS_MODEL,FS_MAIN);PC=compile(VS_COL,FS_MAIN);PL=compile(VS_LINE,FS_LINE);
  PMK=compile(VS_MARK,FS_MARK);
  skyProgram(0);
  if(LIT)PLIT=compile(VS_LIT,FS_LIT);
  B.aniso=gl.getExtension('EXT_texture_filter_anisotropic');
  whiteTex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,whiteTex);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([255,255,255,255]));
  // world geometry
  B.pos=makeBuf(gl.ARRAY_BUFFER,SC.pos);B.uv=makeBuf(gl.ARRAY_BUFFER,SC.uv);B.pick=makeBuf(gl.ARRAY_BUFFER,SC.pick);
  B.tri=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(Math.max(3,SC.tri.length)),gl.DYNAMIC_DRAW);
  B.edge=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(Math.max(2,SC.edge.length)),gl.DYNAMIC_DRAW);
  B.sel=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(3),gl.DYNAMIC_DRAW);
  B.selE=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(2),gl.DYNAMIC_DRAW);
  B.hovE=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(2),gl.DYNAMIC_DRAW);
  B.inside=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(3),gl.DYNAMIC_DRAW);
  B.vTri=worldVAO(B.tri);B.vEdge=worldVAO(B.edge);B.vSel=worldVAO(B.sel);B.vSelE=worldVAO(B.selE);B.vHovE=worldVAO(B.hovE);
  B.vInside=worldVAO(B.inside);
  // the hovered model's or marker's box (positions only; drawn in the accent colour)
  B.hovBox=makeBuf(gl.ARRAY_BUFFER,new Float32Array(3),gl.DYNAMIC_DRAW);
  B.vHovBox=gl.createVertexArray();gl.bindVertexArray(B.vHovBox);attr(0,B.hovBox,3);gl.bindVertexArray(null);
  // textures: average colour until the picture arrives
  for(let i=0;i<TEX.length;i++)GLT.push(colourTex(TEX[i].c||[0.5,0.5,0.5]));
  // pick target: one pixel, drawn through a projection that zooms onto the clicked pixel
  B.pickFB=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,B.pickFB);
  const pt=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,pt);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
  gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,pt,0);
  const rb=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,rb);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT24,1,1);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,rb);
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  // lines (rebuilt when the selection or toggles change)
  const colourVAO=buf=>{const v=gl.createVertexArray();gl.bindVertexArray(v);
    gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,28,0);
    gl.enableVertexAttribArray(7);gl.vertexAttribPointer(7,4,gl.FLOAT,false,28,12);gl.bindVertexArray(null);return v;};
  B.line=gl.createBuffer();B.vLine=colourVAO(B.line);
  // link arrowheads and facing arrows (rebuilt every frame: they face the camera)
  B.head=gl.createBuffer();B.vHead=colourVAO(B.head);
  B.arw=gl.createBuffer();B.vArw=colourVAO(B.arw);
  initMarkers();initModels();initSprites();
  if(LIT)initLitGL();
  initSkyGL();
  sunFlareGL();
  dclGL();
  wxGL();
  glcv.addEventListener('webglcontextlost',e=>{e.preventDefault();
    failLoad('The graphics driver reset the 3D view'+(LT.step?' while turning lights off ('+LT.step+')':'')+'. Reopen the map to continue'+
      (LT.step?' (if this shows again, close the viewer and open the map again, or use Rebuild in viewer).':'.'));});
}
function colourTex(c){const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([c[0]*255|0,c[1]*255|0,c[2]*255|0,255]));return t;}
// Pictures arrive as blobs; decode them in the background and swap them in as they load.
const TEXURL=[];
function blobTexture(blob,mime,done,A){
  const url=URL.createObjectURL(new Blob([(A||D).bytes(blob)],{type:mime||'image/jpeg'}));
  const im=new Image();
  im.onload=()=>{const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.REPEAT);
    if(B.aniso)gl.texParameterf(gl.TEXTURE_2D,B.aniso.TEXTURE_MAX_ANISOTROPY_EXT,4);
    done(t);requestDraw();};
  im.src=url;return url;}
function loadTextures(){
  const load=blobTexture;
  for(let i=0;i<TEX.length;i++){
    const te=TEX[i];
    if(te.b!=null)TEXURL[i]=load(te.b,te.m,t=>{GLT[i]=t;});
    if(te.gb!=null&&LIT)load(te.gb,te.gm,t=>{GLTG[i]=t;});
  }
}

// ---- which world faces are drawn, grouped by texture --------------------------
let MAT=[], matFaces=[], matOrder=[];
function prepMaterials(){
  MAT=TEX.map(matOf);
  matFaces=TEX.map(()=>[]);
  for(let f=0;f<SC.nf;f++)matFaces[SC.faceTex[f]].push(f);
  matOrder=TEX.map((_t,i)=>i).filter(i=>matFaces[i].length);
  cullPrepFaces();
  for(const l of matFaces)l.sort((a,b)=>CULL.fk[a]-CULL.fk[b]||a-b);
}
let faceVis=null;
function faceShown(f){
  if(SC.faceCat[f]&hiddenMask)return false;
  if(THU.hid&&THU.ents&&THU.ents.has(SC.faceEnt[f]))return false;
  if(EXP.hid.size&&EXP.hid.has(SC.faceEnt[f]))return false;
  if(hidEnt.size&&hidEnt.has(SC.faceEnt[f]))return false;
  if(hidPrim.size&&hidPrim.has(SC.facePrim[f]))return false;
  return true;
}
function entShown(ei){const X=ENTS[ei];return !(X.cat&hiddenMask)&&!hidEnt.has(ei)&&!EXP.hid.has(ei)&&!MOD_HID.has(ei);}
// A brush entity whose every face is filtered out (a trigger with Triggers off) loses its
// label, box and links too.
let ENTVIS=null;
function entVisible(ei){return entShown(ei)&&(!ENTS[ei].hasGeo||!ENTVIS||!!ENTVIS[ei]);}
function rebuildWorld(){
  if(!faceVis||faceVis.length!==SC.nf)faceVis=new Uint8Array(SC.nf);
  for(let f=0;f<SC.nf;f++)faceVis[f]=faceShown(f)?1:0;
  ENTVIS=new Uint8Array(MAP.ents.length);for(let f=0;f<SC.nf;f++)if(faceVis[f])ENTVIS[SC.faceEnt[f]]=1;
  renderList();                         // the lists colour what is hidden
  const tri=new Uint32Array(Math.max(3,SC.tri.length));let n=0;
  drawOps=[];drawTrans=[];
  // Every shown face goes into the pick pass. With the game's lighting on, the faces the
  // game draws itself (LIT.rep) are left out of the picture and its own polygons drawn
  // instead, so each texture gets one run of those faces and one of the rest.
  const rep=LIT?LIT.rep:null;
  for(const ti of matOrder){
    for(const want of (rep?[1,0]:[0])){
      const start=n,sg=cullSegs();
      for(const f of matFaces[ti])if(faceVis[f]&&(!rep||rep[f]===want)){const a=SC.faceI0[f],c=SC.faceIN[f];
        sg.add(CULL.fk[f],CULL.fb,f*6,n,c);tri.set(SC.tri.subarray(a,a+c),n);n+=c;}
      if(n>start){const op={ti:ti,start:start,count:n-start,m:MAT[ti],rep:want===1,back:(TEX[ti]||{}).g==='caulk',sky:!!((TEX[ti]||{}).f&TF_SKY),seg:sg.done()};
        (MAT[ti].kind>=2?drawTrans:drawOps).push(op);}
    }
  }
  if(LIT)rebuildLit();
  // see-through surfaces: the game's (liquids, then glass, then additive), and apart
  // from them the editor's volumes, which are drawn last
  drawTrans.sort((a,b)=>({4:0,5:1,2:2,3:3}[a.m.kind]-{4:0,5:1,2:2,3:3}[b.m.kind]));
  drawTransG=drawTrans.filter(op=>!op.m.ed);drawTransE=drawTrans.filter(op=>op.m.ed);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.tri);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,tri.subarray(0,Math.max(3,n)),gl.DYNAMIC_DRAW);
  updateInside(true);
  if(view.wire)rebuildWire();
  rebuildMarkers();rebuildModels();rebuildSelection();lineDirty=true;requestDraw();
}
// ---- see-through brushes the camera is inside ------------------------------------------
// One-sided drawing hides a see-through brush entirely once the camera is inside it.
// MOHRadiant still shows its inner sides then, so those brushes get a second pass with
// the culling flipped. SEE_PRIMS lists every brush with see-through faces.
let SEE_PRIMS=[], insideKey=null, insideOps=[];
function prepSeeThrough(){
  SEE_PRIMS=[];
  SC.prims.forEach((p,pi)=>{if(p.kind!==0)return;
    for(let f=p.f0;f<p.f1;f++){const m=MAT[SC.faceTex[f]];if(m&&m.kind===4&&!m.two){SEE_PRIMS.push(pi);break;}}});
}
function camInsidePrim(p){
  const e=cam.pos;
  if(e[0]<p.mins[0]-1||e[1]<p.mins[1]-1||e[2]<p.mins[2]-1||e[0]>p.maxs[0]+1||e[1]>p.maxs[1]+1||e[2]>p.maxs[2]+1)return false;
  for(let f=p.f0;f<p.f1;f++){const pl=SC.facePlane[f];if(pl&&pl[0]*e[0]+pl[1]*e[1]+pl[2]*e[2]-pl[3]>0.5)return false;}
  return true;
}
function updateInside(force){
  if(!faceVis)return;
  const inside=[];
  for(const pi of SEE_PRIMS)if(camInsidePrim(SC.prims[pi]))inside.push(pi);
  const key=inside.join(',');
  if(key===insideKey&&!force)return;
  insideKey=key;
  const byTex=new Map();
  for(const pi of inside){const p=SC.prims[pi];
    for(let f=p.f0;f<p.f1;f++){if(!faceVis[f])continue;const ti=SC.faceTex[f],m=MAT[ti];if(!m||m.kind!==4||m.two)continue;
      let l=byTex.get(ti);if(!l){l=[];byTex.set(ti,l);}l.push(f);}}
  const tri=[];insideOps=[];
  for(const[ti,fs]of byTex){const start=tri.length;
    for(const f of fs){const a=SC.faceI0[f],c=SC.faceIN[f];for(let k=a;k<a+c;k++)tri.push(SC.tri[k]);}
    insideOps.push({ti:ti,start:start,count:tri.length-start,m:MAT[ti]});}
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.inside);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(tri.length?tri:[0,0,0]),gl.DYNAMIC_DRAW);
}
function rebuildWire(){
  const e=new Uint32Array(Math.max(2,SC.edge.length));let n=0;
  for(let f=0;f<SC.nf;f++)if(faceVis[f]){const a=SC.faceE0[f],c=SC.faceEN[f];e.set(SC.edge.subarray(a,a+c),n);n+=c;}
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.edge);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,e.subarray(0,Math.max(2,n)),gl.DYNAMIC_DRAW);
  wireCount=n;
}

// ---- point-entity markers: boxes coloured like MOHRadiant, lights as diamonds -----------
// (VS_MARK / FS_MARK say what each vertex carries)
function initMarkers(){
  const P=[],Cc=[],K=[],Q=[],O=[];
  for(const X of ENTS){
    X.mv0=P.length/3;X.mvn=0;
    if(!X.marker)continue;
    const o=X.origin, b=X.mbox||X.box||{mins:[-8,-8,-8],maxs:[8,8,8]}, id=NF+1+X.ei, ol=X.ol?[X.ol[0],X.ol[1],X.ol[2],1]:[0,0,0,0];
    const push=(v,c,m,q)=>{P.push(v[0],v[1],v[2]);Cc.push(c[0],c[1],c[2],m);K.push(id);Q.push(q[0],q[1],q[2]);O.push(ol[0],ol[1],ol[2],ol[3]);};
    if(X.marker===2){
      const c=X.col, lo=[c[0]*0.75,c[1]*0.75,c[2]*0.75], mid=[0.5,0.5,0.5];
      const r=8,v=[[o[0]+r,o[1],o[2]],[o[0],o[1]+r,o[2]],[o[0]-r,o[1],o[2]],[o[0],o[1]-r,o[2]]],up=[o[0],o[1],o[2]+r],dn=[o[0],o[1],o[2]-r];
      for(let k=0;k<4;k++){const a=v[k],q=v[(k+1)%4];
        push(up,c,3,mid);push(q,c,3,mid);push(a,c,3,mid);
        push(dn,lo,3,mid);push(a,lo,3,mid);push(q,lo,3,mid);}
    }else{
      const mn=[o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]],mx=[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]];
      const c=X.mcol||X.col, m=X.mk==null?1:X.mk;
      const Cn=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]];
      // six faces, wound clockwise seen from outside: bottom, top, -y, +y, -x, +x
      const faces=[[3,2,0,1],[6,7,5,4],[0,4,5,1],[7,6,2,3],[6,4,0,2],[5,7,3,1]], axis=[2,2,1,1,0,0];
      for(let f=0;f<6;f++){const q=faces[f];
        const U=k=>{const u=[k&1?1:0,k&2?1:0,k&4?1:0];u[axis[f]]=0.5;return u;};
        for(const k of [q[0],q[1],q[2],q[0],q[2],q[3]])push(Cn(k),c,m,U(k));}
    }
    X.mvn=P.length/3-X.mv0;
  }
  B.mPos=makeBuf(gl.ARRAY_BUFFER,new Float32Array(P.length?P:[0,0,0]));B.mCol=makeBuf(gl.ARRAY_BUFFER,new Float32Array(Cc.length?Cc:[0,0,0,0]));
  B.mPick=makeBuf(gl.ARRAY_BUFFER,new Float32Array(K.length?K:[0]));
  B.mBox=makeBuf(gl.ARRAY_BUFFER,new Float32Array(Q.length?Q:[0,0,0]));B.mOl=makeBuf(gl.ARRAY_BUFFER,new Float32Array(O.length?O:[0,0,0,0]));
  B.mIdx=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(Math.max(3,P.length/3)),gl.DYNAMIC_DRAW);
  B.vMark=gl.createVertexArray();gl.bindVertexArray(B.vMark);attr(0,B.mPos,3);attr(7,B.mCol,4);attr(2,B.mPick,1);attr(8,B.mBox,3);attr(10,B.mOl,4);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.mIdx);gl.bindVertexArray(null);
  B.mSel=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(3),gl.DYNAMIC_DRAW);
  B.vMarkSel=gl.createVertexArray();gl.bindVertexArray(B.vMarkSel);attr(0,B.mPos,3);attr(7,B.mCol,4);attr(2,B.mPick,1);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.mSel);gl.bindVertexArray(null);
}
let markSelCount=0;
function rebuildMarkers(){
  const idx=[];
  for(const X of ENTS)if(X.mvn&&entShown(X.ei))for(let k=0;k<X.mvn;k++)idx.push(X.mv0+k);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.mIdx);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(idx.length?idx:[0,0,0]),gl.DYNAMIC_DRAW);
  boxCount=idx.length;
}

// ---- models: one mesh per model, drawn once per entity that uses it --------------
const MODELS=[];
function instRows(X){
  const e=MAP.ents[X.ei], ax=anglesAxis(entAngles(e.kvl)), s=parseFloat(e.kvl.scale)||1, o=X.origin;
  return [ax[0][0]*s,ax[1][0]*s,ax[2][0]*s,o[0], ax[0][1]*s,ax[1][1]*s,ax[2][1]*s,o[1], ax[0][2]*s,ax[1][2]*s,ax[2][2]*s,o[2]];
}
// Per instance: three rows of the placement matrix, the pick id, then its light for the
// game's lighting: light grid colour and the first vertex of its baked light (or -1), and
// its slot among the lights' probes (its grid colour relit with a light off; -1: none).
const INST_FLOATS=19;
function instData(ei){
  const X=ENTS[ei], rows=instRows(X), L=D.lit, g=L&&L.el?L.el[ei]:null, st=L&&L.st?L.st[ei]:null;
  const slot=LT.entSlot&&LT.entSlot.has(ei)?LT.entSlot.get(ei):-1;
  return rows.concat([NF+1+ei, g?g[0]/255:1, g?g[1]/255:1, g?g[2]/255:1, st!=null?st:-1, slot, isStaticProp(ei)?1:0]);
}
function initModels(){
  (D.models||[]).forEach(M=>MODELS.push(modelR(M,D)));
  for(const X of ENTS)if(X.model>=0)MODELS[X.model].inst.push(X.ei);
}
// one model's mesh on the card, from a packet (A: the page's data, or Simulate's model)
function modelR(M,A){
    const R={M:M,pos:A.f32(M.v),uv:A.f32(M.t),idx:A.u32(M.i),inst:[],n:0,nsel:0,sprites:[]};
    // A tree's sprite version (TF_LOD) is drawn only with Simple models on (surfOn); other
    // camera-facing sprite surfaces (coronas) are drawn as billboards (drawSprites).
    R.surfs=M.s.map(s=>{const f=(TEX[s[2]]||{}).f|0, lod=!!(f&TF_LOD);
      return {first:s[0],count:s[1],ti:s[2],name:s[3],v0:s[4]|0,vn:s[5]|0,lod:lod,sprite:!lod&&!!(f&TF_SPRITE)};});
    R.hasLod=R.surfs.some(s=>s.lod);
    R.vbP=makeBuf(gl.ARRAY_BUFFER,R.pos);R.vbT=makeBuf(gl.ARRAY_BUFFER,R.uv);R.ib=makeBuf(gl.ELEMENT_ARRAY_BUFFER,R.idx);
    // each vertex's number in the engine's own order, to find its baked light
    const eng=new Float32Array(R.pos.length/3);
    for(const s of M.s)if(s.length>=7)for(let k=0;k<s[5];k++)eng[s[4]+k]=s[6]+k;
    R.vbE=makeBuf(gl.ARRAY_BUFFER,eng);R.eng=eng;
    // the vertex normals (signed bytes), for deformVertexes; which surfaces move
    if(M.n!=null){const nb=A.i8(M.n);if(nb.length>=R.pos.length)R.vbN=makeBuf(gl.ARRAY_BUFFER,nb);}
    R.dv=!!R.vbN&&R.surfs.some(s=>(TEX[s.ti]||{}).dv);
    const a2=R.hasLod?auto2Data(R):null;
    if(a2){R.vbA2=makeBuf(gl.ARRAY_BUFFER,a2.mid);R.vbA2M=makeBuf(gl.ARRAY_BUFFER,a2.axis);}
    R.instBuf=gl.createBuffer();R.selBuf=gl.createBuffer();
    const st=INST_FLOATS*4;
    const mk=buf=>{const v=gl.createVertexArray();gl.bindVertexArray(v);attr(0,R.vbP,3);attr(1,R.vbT,2);attr(9,R.vbE,1);
      if(a2){attr(11,R.vbA2,4);attr(12,R.vbA2M,3);}
      gl.bindBuffer(gl.ARRAY_BUFFER,buf);
      for(let k=0;k<3;k++){gl.enableVertexAttribArray(3+k);gl.vertexAttribPointer(3+k,4,gl.FLOAT,false,st,k*16);gl.vertexAttribDivisor(3+k,1);}
      gl.enableVertexAttribArray(6);gl.vertexAttribPointer(6,1,gl.FLOAT,false,st,48);gl.vertexAttribDivisor(6,1);
      gl.enableVertexAttribArray(10);gl.vertexAttribPointer(10,4,gl.FLOAT,false,st,52);gl.vertexAttribDivisor(10,1);
      gl.enableVertexAttribArray(15);gl.vertexAttribPointer(15,1,gl.FLOAT,false,st,68);gl.vertexAttribDivisor(15,1);
      gl.enableVertexAttribArray(13);gl.vertexAttribPointer(13,1,gl.FLOAT,false,st,72);gl.vertexAttribDivisor(13,1);
      if(R.vbN){gl.bindBuffer(gl.ARRAY_BUFFER,R.vbN);gl.enableVertexAttribArray(14);gl.vertexAttribPointer(14,3,gl.BYTE,true,0,0);}
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,R.ib);gl.bindVertexArray(null);return v;};
    R.vao=mk(R.instBuf);R.vaoSel=mk(R.selBuf);
    for(const s of R.surfs)if(s.sprite){let c=[0,0,0],n=0,r=0;
      for(let k=s.first;k<s.first+s.count;k++){const v=R.idx[k];c[0]+=R.pos[v*3];c[1]+=R.pos[v*3+1];c[2]+=R.pos[v*3+2];n++;}
      c=c.map(x=>x/Math.max(1,n));
      for(let k=s.first;k<s.first+s.count;k++){const v=R.idx[k];r=Math.max(r,Math.hypot(R.pos[v*3]-c[0],R.pos[v*3+1]-c[1],R.pos[v*3+2]-c[2]));}
      s.c=c;s.r=r;R.sprites.push(s);}
    return R;
}
// the models drawScene draws: the map's, and Simulate's while it flies (not in the pick
// pass: it is clicked through)
function modelsDrawn(mode){
  let L=(mode===0&&SIM.R&&SIM.R.n)?MODELS.concat([SIM.R]):MODELS;
  if(mode===0&&MOD.ents.length){const mr=modModelsInst();if(mr.length)L=L.concat(mr);}
  if(mode===0&&ACT.cur){const ar=actDrawn();if(ar)L=L.concat(ar);}
  return L;}
// Which of a model's surfaces are drawn: never its camera-facing sprites (drawSprites
// draws those); a tree that has a sprite version shows the sprite alone with Simple models
// on, and everything but the sprite with it off.
function surfOn(R,s){return !s.sprite&&((simpleModels&&R.hasLod)?s.lod:!s.lod);}
// Autosprite2Deform's set-up for each quad of a sprite version, four vertices in a row as
// the engine takes them: the two shortest of the six vertex pairs are the quad's ends and
// the line between their middles its long axis. Each vertex keeps its end's middle and
// half that end's length, signed for the side it goes to (the engine's v1 / v3 one way,
// v2 / v4 the other), so the quad is rebuilt about its axis without being mirrored.
const A2_EDGES=[[0,1],[0,3],[0,2],[1,3],[1,2],[3,2]];
function auto2Data(R){
  const P=R.pos, nv=P.length/3, mid=new Float32Array(nv*4), axis=new Float32Array(nv*3), E=A2_EDGES;
  for(const s of R.surfs){if(!s.lod)continue;
    for(let q=s.v0;q+4<=s.v0+s.vn&&q+4<=nv;q+=4){
      const at=k=>[P[(q+k)*3],P[(q+k)*3+1],P[(q+k)*3+2]];
      const sl=[1e9,1e9],sn=[0,0],ll=[0,0],ln=[0,0];
      for(let j=0;j<6;j++){const a=at(E[j][0]),b=at(E[j][1]);
        const l=(a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2;
        if(l<sl[0]){sn[1]=sn[0];sl[1]=sl[0];sn[0]=j;sl[0]=l;}else if(l<sl[1]){sn[1]=j;sl[1]=l;}
        if(l>ll[0]){ln[1]=ln[0];ll[1]=ll[0];ln[0]=j;ll[0]=l;}else if(l>ll[1]){ln[1]=j;ll[1]=l;}}
      const md=[0,1].map(j=>{const a=at(E[sn[j]][0]),b=at(E[sn[j]][1]);return[(a[0]+b[0])/2,(a[1]+b[1])/2,(a[2]+b[2])/2];});
      const ax=[md[1][0]-md[0][0],md[1][1]-md[0][1],md[1][2]-md[0][2]];
      const onEdge=(k,j)=>k===E[j][0]||k===E[j][1];
      const same=onEdge(E[sn[0]][0],ln[0])===onEdge(E[sn[1]][0],ln[1]);
      const h0=Math.sqrt(sl[0])*0.5, h1=Math.sqrt(sl[1])*0.5;
      const put=[[E[sn[0]][0],0,-h0],[E[sn[0]][1],0,h0],[E[sn[1]][same?0:1],1,-h1],[E[sn[1]][same?1:0],1,h1]];
      for(const[k,j,h]of put){mid.set([md[j][0],md[j][1],md[j][2],h],(q+k)*4);axis.set(ax,(q+k)*3);}
    }}
  return {mid:mid,axis:axis};
}
function rebuildModels(){
  for(const R of MODELS){
    const a=[],sp=[],M=R.M,b=M&&M.b;
    for(const ei of R.inst)if(entShown(ei)){const d=instData(ei);a.push(...d);
      // its bounding sphere, for culling (cullModels): the model's box turned and scaled
      if(b){const c=[(b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2,(b[0][2]+b[1][2])/2],h=Math.hypot(b[1][0]-b[0][0],b[1][1]-b[0][1],b[1][2]-b[0][2])/2,
          sc=Math.max(Math.hypot(d[0],d[4],d[8]),Math.hypot(d[1],d[5],d[9]),Math.hypot(d[2],d[6],d[10]));
        sp.push(d[0]*c[0]+d[1]*c[1]+d[2]*c[2]+d[3],d[4]*c[0]+d[5]*c[1]+d[6]*c[2]+d[7],d[8]*c[0]+d[9]*c[1]+d[10]*c[2]+d[11],h*sc+16);}
      else sp.push(d[3],d[7],d[11],1e9);}
    R.all=new Float32Array(a.length?a:new Array(INST_FLOATS).fill(0));R.sph=new Float32Array(sp);R.full=a.length/INST_FLOATS;
    R.stage=new Float32Array(R.all.length);R.vis=null;
    gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,R.all,gl.DYNAMIC_DRAW);
    R.n=R.full;
  }
}
// How a model surface is lit in game (tr_shader.c rgbGen): 2 baked vertex light on a
// static prop (else the grid), 1 the light grid, 0 as it is.
function modelLitMode(ti){
  const te=TEX[ti];if(!te)return 1;
  if(te.noshader||te.standin)return 1;           // no shader script: lightingGrid
  const rg=te.rg||'';
  if(rg==='lightingspherical'||rg==='static'||rg==='vertex'||rg==='exactvertex')return 2;
  if(rg==='lightinggrid'||rg==='lightingdiffuse')return 1;
  return 0;
}
// sprite billboards, rebuilt every frame from the camera's axes
function initSprites(){B.spP=gl.createBuffer();B.spT=gl.createBuffer();B.spK=gl.createBuffer();
  B.vSp=gl.createVertexArray();gl.bindVertexArray(B.vSp);attr(0,B.spP,3);attr(1,B.spT,2);attr(2,B.spK,1);gl.bindVertexArray(null);}

// ============================================================================
//  The game's lighting (Full Brightness off; a .bsp only)
// ============================================================================
// The game doesn't draw the .map's brush faces: it draws the compiled polygons, lit by
// the lightmaps (or vertex light) the map compiler baked. LIT gathers those, each tied
// to the .map face, patch or terrain block it came from, so the Show filters, hiding
// and selection keep working on them:
//   planar polygons  straight from the .bsp (positions, texture and lightmap coordinates)
//   patches          the .map patch, with the .bsp's lightmap coordinates and vertex
//                    light per control point carried through the same curves
//   terrain          the .map terrain, with lightmap coordinates from each patch's
//                    corner texel and scale (tr_terrain.c R_PreTessellateTerrain)
// LIT.rep marks the .map faces those replace (everything the game draws; editor
// textures such as caulk, clips and triggers keep their .map faces).
const EDITOR_GROUPS={caulk:1,clip:1,trigger:1,origin:1,hint:1,skip:1,portal:1,nodraw:1,ladder:1};
function buildLit(){
  const L=D.lit;if(!L)return null;
  const key=(e,b)=>e*1048576+b, primOf=new Map();
  SC.prims.forEach((p,pi)=>primOf.set(key(p.ent,p.bn),pi));
  const faceOf=(pi,k)=>{const p=SC.prims[pi];for(let f=p.f0;f<p.f1;f++)if(SC.faceSide[f]===k)return f;return -1;};
  const rep=new Uint8Array(SC.nf);
  // faces whose texture the game draws are replaced by its polygons
  for(let f=0;f<SC.nf;f++)if(SC.faceKind[f]===0){const te=TEX[SC.faceTex[f]];if(te&&!(te.f&TF_NODRAW)&&!EDITOR_GROUPS[te.g])rep[f]=1;}
  // patches and terrain blocks that have the game's light
  const pats=[],ters=[];
  for(const r of (L.p||[])){const pi=primOf.get(key(r[0],r[1]));if(pi==null)continue;const p=SC.prims[pi];
    if(p.kind!==1||p.f1<=p.f0||r[2]===-3)continue;pats.push([r,pi,p.f0]);}
  for(const r of (L.t||[])){const pi=primOf.get(key(0,r[0]));if(pi==null)continue;const p=SC.prims[pi];
    if(p.kind!==2)continue;for(let f=p.f0;f<p.f1;f++)ters.push([r,pi,f]);}
  const bp=L.ns?D.f32(L.v):new Float32Array(0), nb=bp.length/3, bi=L.ns?D.u32(L.i):new Uint32Array(0);
  let nv=nb, ni=bi.length;
  for(const[,,f]of pats){nv+=SC.faceVN[f];ni+=SC.faceIN[f];}
  for(const[,,f]of ters){nv+=SC.faceVN[f];ni+=SC.faceIN[f];}
  const pos=new Float32Array(nv*3), uv=new Float32Array(nv*2), lm=new Float32Array(nv*3), col=new Uint8Array(nv*4), tri=new Uint32Array(Math.max(3,ni));
  const nrm=new Float32Array(nv*3);   // a patch's normals (the .bsp's, the side it is lit on), for LT
  const units=[];          // {i0, n, ti, f, pi, ei}
  if(L.ns){
    pos.set(bp);uv.set(D.f32(L.uv));lm.set(D.f32(L.l));col.set(D.bytes(L.c));tri.set(bi);
    const s=D.i32(L.s);
    for(let k=0;k<L.ns;k++){const o=k*6, e=s[o+3], b=s[o+4], fk=s[o+5];
      const pi=b>=0?primOf.get(key(e,b)):undefined, f=(pi!=null&&fk>=0)?faceOf(pi,fk):-1;
      units.push({i0:s[o],n:s[o+1],ti:s[o+2],f:f,pi:pi!=null?pi:-1,ei:e,k:0});}
  }
  let v=nb, t=bi.length;
  // copy a .map face's geometry, with fill() for its light; k: 1 a patch, 2 terrain (a
  // .bsp polygon is 0)
  const addFace=(f,ti,pi,ei,fill,k)=>{
    const v0=SC.faceV0[f], vn=SC.faceVN[f];
    pos.set(SC.pos.subarray(v0*3,(v0+vn)*3),v*3);uv.set(SC.uv.subarray(v0*2,(v0+vn)*2),v*2);
    for(let q=0;q<vn;q++)fill(q,v+q);
    const a=SC.faceI0[f],c=SC.faceIN[f];
    for(let q=0;q<c;q++)tri[t+q]=SC.tri[a+q]-v0+v;
    units.push({i0:t,n:c,ti:ti,f:f,pi:pi,ei:ei,k:k});v+=vn;t+=c;rep[f]=1;};
  const pl=L.pl!=null?D.f32(L.pl):null, pc=L.pc!=null?D.bytes(L.pc):null, pn=L.pn!=null?D.f32(L.pn):null;
  for(const[r,pi,f]of pats){
    const P=SC.prims[pi], Pd=MAP.ents[P.ent].prims[P.bn].d, cnt=r[4], layer=r[2];
    if(!pl||Pd.w*Pd.h!==cnt)continue;
    const X=new Float64Array(cnt*9);
    for(let q=0;q<cnt;q++){X[q*9]=pl[(r[3]+q)*2];X[q*9+1]=pl[(r[3]+q)*2+1];
      for(let k=0;k<4;k++)X[q*9+2+k]=pc[(r[3]+q)*4+k];
      if(pn)for(let k=0;k<3;k++)X[q*9+6+k]=pn[(r[3]+q)*3+k];}
    const g=tessPatch(Pd,X,9);
    if(!g||g.cols*g.rows!==SC.faceVN[f])continue;
    addFace(f,SC.faceTex[f],pi,P.ent,(q,o)=>{
      lm[o*3]=g.x[q*9];lm[o*3+1]=g.x[q*9+1];lm[o*3+2]=layer;
      for(let k=0;k<4;k++)col[o*4+k]=Math.max(0,Math.min(255,Math.round(g.x[q*9+2+k])));
      for(let k=0;k<3;k++)nrm[o*3+k]=g.x[q*9+6+k];},1);
  }
  for(const[r,pi,f]of ters){
    const P=SC.prims[pi], org=MAP.ents[P.ent].prims[P.bn].d.org;
    addFace(f,SC.faceTex[f],pi,P.ent,(q,o)=>{
      const i=(pos[o*3]-org[0])/64, j=(pos[o*3+1]-org[1])/64;
      lm[o*3]=r[2]+i*r[4];lm[o*3+1]=r[3]+j*r[4];lm[o*3+2]=r[1];
      col[o*4]=col[o*4+1]=col[o*4+2]=col[o*4+3]=255;},2);
  }
  const byTex=new Map();
  units.forEach((u,k)=>{if(!u.n)return;let l=byTex.get(u.ti);if(!l){l=[];byTex.set(u.ti,l);}l.push(k);});
  return {nv:v,pos:pos.subarray(0,v*3),uv:uv.subarray(0,v*2),lm:lm.subarray(0,v*3),col:col.subarray(0,v*4),nrm:nrm.subarray(0,v*3),
          tri:tri.subarray(0,Math.max(3,t)),units:units,byTex:byTex,rep:rep,ops:[],trans:[],sky:[]};
}
function initLitGL(){
  B.lPos=makeBuf(gl.ARRAY_BUFFER,LIT.pos);B.lUV=makeBuf(gl.ARRAY_BUFFER,LIT.uv);
  B.lLM=makeBuf(gl.ARRAY_BUFFER,LIT.lm);B.lCol=makeBuf(gl.ARRAY_BUFFER,LIT.col);
  B.lTri=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(LIT.tri.length),gl.DYNAMIC_DRAW);
  B.vLit=gl.createVertexArray();gl.bindVertexArray(B.vLit);attr(0,B.lPos,3);attr(1,B.lUV,2);attr(8,B.lLM,3);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.lCol);gl.enableVertexAttribArray(7);gl.vertexAttribPointer(7,4,gl.UNSIGNED_BYTE,true,0,0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.lTri);gl.bindVertexArray(null);
  const L=D.lit;
  // lightmap pages: white until the picture is decoded. The page holds the .bsp's own
  // bytes (raw); they are brightened here as the game does it, and kept for r_lightmap 2.
  B.lmTex=arrayTex(1,1,1,new Uint8Array([255,255,255,255]));
  if(L.lm!=null){const url=URL.createObjectURL(new Blob([D.bytes(L.lm)],{type:'image/png'})),im=new Image();
    im.onload=()=>{try{
      const cv=document.createElement('canvas');cv.width=im.width;cv.height=im.height;const c2=cv.getContext('2d');c2.drawImage(im,0,0);
      const px=c2.getImageData(0,0,im.width,im.height).data, S=128, n=L.nlm, cols=L.cols, out=new Uint8Array(S*S*4*n);
      for(let k=0;k<n;k++){const ox=(k%cols)*S, oy=Math.floor(k/cols)*S;
        for(let y=0;y<S;y++)out.set(px.subarray(((oy+y)*im.width+ox)*4,((oy+y)*im.width+ox+S)*4),(k*S*S+y*S)*4);}
      B.lmRaw=L.raw?out:null;B.lmN=n;
      const t=arrayTex(S,S,n,L.raw?lmShift(out,L.shift|0):out);gl.deleteTexture(B.lmTex);B.lmTex=t;
      if(B.lmHeat){gl.deleteTexture(B.lmHeat);B.lmHeat=null;}
      requestDraw();
    }catch(e){console.warn('lightmaps',e);}URL.revokeObjectURL(url);};
    im.src=url;}
  // baked light of the static props, one texel per vertex, 4096 across
  if(L.sm!=null&&L.smn){const W2=4096,H2=Math.ceil(L.smn/W2),src=D.bytes(L.sm),data=new Uint8Array(W2*H2*3);data.set(src.subarray(0,Math.min(src.length,data.length)));
    B.smTex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,B.smTex);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB8,W2,H2,0,gl.RGB,gl.UNSIGNED_BYTE,data);gl.pixelStorei(gl.UNPACK_ALIGNMENT,4);
    for(const p of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,p,gl.NEAREST);}
  else B.smTex=colourTex([1,1,1]);
}
// R_ColorShiftLightingBytes: each channel shifted up (the overbright bits), and a texel
// that goes past 255 scaled back by its brightest channel, so it keeps its colour
function lmShift(raw,sh){const out=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i+=4){let r=raw[i]<<sh,g=raw[i+1]<<sh,b=raw[i+2]<<sh;
    if((r|g|b)>255){const m=Math.max(r,g,b);r=Math.floor(r*255/m);g=Math.floor(g*255/m);b=Math.floor(b*255/m);}
    out[i]=r;out[i+1]=g;out[i+2]=b;out[i+3]=255;}
  return out;}
// r_lightmap 2 (R_LoadLightmaps): each texel coloured by the intensity of its raw bytes,
// 0.33 red + 0.685 green + 0.063 blue out of 255, through HSVtoRGB (hue times 5, full
// saturation, value 0.5), in the game's float arithmetic; the brightest is reported
function lmHeat(){
  if(B.lmHeat||!B.lmRaw)return B.lmHeat||null;
  const raw=B.lmRaw,out=new Uint8Array(raw.length),f=Math.fround;let mx=0;
  for(let i=0;i<raw.length;i+=4){
    let I=f(f(f(f(0.33)*raw[i])+f(f(0.685)*raw[i+1]))+f(f(0.063)*raw[i+2]));
    I=I>255?1:f(I/255);if(I>mx)mx=I;
    const h=f(I*5),k=Math.floor(h),fr=f(h-k),q=f(0.5*f(1-fr)),t=f(0.5*fr);
    const c=k===0?[0.5,t,0]:k===1?[q,0.5,0]:k===2?[0,0.5,t]:k===3?[0,q,0.5]:k===4?[t,0,0.5]:[0.5,0,q];
    out[i]=Math.trunc(f(c[0]*255));out[i+1]=Math.trunc(f(c[1]*255));out[i+2]=Math.trunc(f(c[2]*255));out[i+3]=255;}
  B.lmBright=Math.trunc(f(mx*255));
  B.lmHeat=arrayTex(128,128,B.lmN,out);
  return B.lmHeat;}
// r_lightmap: does this texture's shader show the lightmap alone (the builder works it out
// from its stages; a texture with no shader gets the game's own two-stage one, which does)
function lmOnly(ti){const te=TEX[ti];return !!(te&&(te.lmr||te.noshader));}
// The sky boxes (a .bsp's and a .map's): six pictures each, one array texture per box.
function initSkyGL(){
  const S0=D.sky||[];
  B.skyNone=arrayTex(1,1,1,new Uint8Array([0,0,0,255]));
  B.skyTex=S0.map(()=>null);
  S0.forEach((faces,si)=>{
    const ims=faces.map(b=>{const im=new Image();im.src=URL.createObjectURL(new Blob([D.bytes(b)],{type:'image/jpeg'}));return im;});
    Promise.all(ims.map(im=>im.decode().then(()=>im,()=>null))).then(list=>{
      if(list.some(im=>!im))return;
      const S=Math.max(...list.map(im=>Math.max(im.width,im.height)));
      const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D_ARRAY,t);gl.texStorage3D(gl.TEXTURE_2D_ARRAY,1,gl.RGBA8,S,S,6);
      const cv=document.createElement('canvas');cv.width=cv.height=S;const c2=cv.getContext('2d');
      list.forEach((im,k)=>{c2.clearRect(0,0,S,S);c2.drawImage(im,0,0,S,S);
        gl.texSubImage3D(gl.TEXTURE_2D_ARRAY,0,0,0,k,S,S,1,gl.RGBA,gl.UNSIGNED_BYTE,cv);URL.revokeObjectURL(im.src);});
      for(const[p,v]of[[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])
        gl.texParameteri(gl.TEXTURE_2D_ARRAY,p,v);
      B.skyTex[si]=t;requestDraw();});
  });
  // the cloud layers: one picture per stage, tiled
  CLOUDS=(D.clouds||[]).map(c=>({h:c.h,s:c.s.map(st=>{const L=Object.assign({tex:null},st);
    blobTexture(st.b,st.m,t=>{L.tex=t;});return L;})}));
  const moving=L=>L.tm.some(m=>(m[0]==='scroll'&&(m[1]||m[2]))||(m[0]==='rotate'&&m[1]&&m[3])||
    ((m[0]==='stretch'||m[0]==='wavetrans'||m[0]==='wavetrant')&&m[3]&&m[5]))||
    ((L.rg[0]==='w'&&L.rg[3]&&L.rg[5])||(L.rg[0]==='cw'&&L.rg[6]&&L.rg[8]))||(L.ag[0]==='w'&&L.ag[3]&&L.ag[5]);
  for(const c of CLOUDS)c.mv=c.s.some(moving);
  CLOUDS_MOVE=CLOUDS.some(c=>c.mv);
  const sa=parseFloat((MAP.ents[0]||{kvl:{}}).kvl.skyalpha);
  SKY_ALPHA=isFinite(sa)?sa:1;
}
// ---- the sky's cloud layers ----------------------------------------------------------
// Each stage's tcMods, rgbGen and alphaGen are worked out once a frame from the time since
// the page opened (the game's shaderTime counts from the level's start), the tcMods folded
// into one affine map for skyFS. Waves read the engine's tables (tr_init.c, 1024 steps).
let CLOUDS=[], CLOUDS_MOVE=false, SKY_ALPHA=1;
const T0=performance.now(), FUNC_N=1024;
const FUNC={sin:new Float32Array(FUNC_N),square:new Float32Array(FUNC_N),triangle:new Float32Array(FUNC_N),
  sawtooth:new Float32Array(FUNC_N),inversesawtooth:new Float32Array(FUNC_N)};
for(let i=0;i<FUNC_N;i++){
  FUNC.sin[i]=Math.sin(i*2*Math.PI/(FUNC_N-1));FUNC.square[i]=i<FUNC_N/2?1:-1;
  FUNC.sawtooth[i]=i/FUNC_N;FUNC.inversesawtooth[i]=1-i/FUNC_N;
  FUNC.triangle[i]=i<FUNC_N/2?(i<FUNC_N/4?i/(FUNC_N/4):1-FUNC.triangle[i-FUNC_N/4]):-FUNC.triangle[i-FUNC_N/2];}
// smooth noise in -1..1 for the "noise" waveform (the engine's R_NoiseGet4f is a lattice
// noise of the same kind; its exact values aren't reproduced)
function noise1(x){const i=Math.floor(x),f=x-i,u=f*f*(3-2*f),
  h=n=>{const v=Math.sin(n*127.1+311.7)*43758.5453;return(v-Math.floor(v))*2-1;};return h(i)*(1-u)+h(i+1)*u;}
// [function, base, amplitude, phase, frequency] at time T (EvalWaveForm)
function waveAt(w,T){
  if(w[0]==='noise')return w[1]+noise1((T+w[3])*w[4])*w[2];
  return w[1]+(FUNC[w[0]]||FUNC.sin)[Math.trunc((w[3]+T*w[4])*FUNC_N)&(FUNC_N-1)]*w[2];}
const clamp01=x=>Math.max(0,Math.min(1,x));
// one stage at time T: the rows of its affine texture-coordinate map and its colour
function cloudStage(L,T){
  let a=1,b=0,c=0,d=0,e=1,f=0;
  const then=(A,B2,C,D2,E,F)=>{const na=A*a+B2*d,nb=A*b+B2*e,nc=A*c+B2*f+C,nd=D2*a+E*d,ne=D2*b+E*e,nf=D2*c+E*f+F;
    a=na;b=nb;c=nc;d=nd;e=ne;f=nf;};
  for(const m of L.tm){
    if(m[0]==='scroll'){let s=m[1]*T,t=m[2]*T;s-=Math.floor(s);t-=Math.floor(t);then(1,0,s,0,1,t);}
    else if(m[0]==='scale')then(m[1],0,0,0,m[2],0);
    else if(m[0]==='offset')then(1,0,m[1],0,1,m[2]);
    else if(m[0]==='transform')then(m[1],m[3],m[5],m[2],m[4],m[6]);
    else if(m[0]==='rotate'){const i=Math.trunc((-m[1]*m[3]*T-m[2])*(FUNC_N/360)),
      sn=FUNC.sin[i&(FUNC_N-1)],cs=FUNC.sin[(i+FUNC_N/4)&(FUNC_N-1)];
      then(cs,-sn,0.5-0.5*cs+0.5*sn,sn,cs,0.5-0.5*sn-0.5*cs);}
    else if(m[0]==='stretch'){const w=waveAt(m.slice(1),T),p=w?1/w:1;then(p,0,0.5-0.5*p,0,p,0.5-0.5*p);}
    else if(m[0]==='wavetrans')then(1,0,waveAt(m.slice(1),T),0,1,0);
    else if(m[0]==='wavetrant')then(1,0,0,0,1,waveAt(m.slice(1),T));
  }
  const rg=L.rg, ag=L.ag;let r=1,g=1,bl=1,al=1;
  if(rg[0]==='c'){r=rg[1];g=rg[2];bl=rg[3];}
  else if(rg[0]==='w')r=g=bl=clamp01(waveAt(rg.slice(1),T));
  else if(rg[0]==='cw'){const v=clamp01(waveAt(rg.slice(4),T));r=rg[1]*v;g=rg[2]*v;bl=rg[3]*v;}
  if(ag[0]==='c')al=ag[1];else if(ag[0]==='w')al=clamp01(waveAt(ag.slice(1),T));
  else if(ag[0]==='sky')al=SKY_ALPHA;else if(ag[0]==='1sky')al=1-SKY_ALPHA;
  return{A:[a,b,c],B:[d,e,f],C:[r,g,bl,al]};
}
// The stages of one sky's cloud layers drawn now: a stage whose picture hasn't loaded yet
// waits, and a skyAlpha stage is skipped at no sky alpha, as in RB_IterateStagesGeneric.
function cloudLayers(C){
  const out=[];
  if(C)for(const L of C.s){if(out.length>=4)break;if(!L.tex)continue;
    if((L.ag[0]==='sky'&&SKY_ALPHA<0.01)||(L.ag[0]==='1sky'&&SKY_ALPHA>0.99))continue;out.push(L);}
  return out;
}
// their pictures (texture units 4 to 7) and uniforms at time T
function setClouds(P,C,list,T){
  const A=new Float32Array(12),Bv=new Float32Array(12),Cc=new Float32Array(16),F=new Int32Array(12);
  list.forEach((L,n)=>{const r=cloudStage(L,T);A.set(r.A,n*3);Bv.set(r.B,n*3);Cc.set(r.C,n*4);F.set(L.f,n*3);
    gl.activeTexture(gl.TEXTURE4+n);gl.bindTexture(gl.TEXTURE_2D,L.tex);});
  gl.activeTexture(gl.TEXTURE0);
  gl.uniform1f(P.u.uCH,C.h);gl.uniform3fv(P.u['uCA[0]'],A);gl.uniform3fv(P.u['uCB[0]'],Bv);
  gl.uniform4fv(P.u['uCC[0]'],Cc);gl.uniform3iv(P.u['uCF[0]'],F);
}
// Moving clouds keep the view redrawing while the game's sky is on screen. An occlusion
// query on each frame's sky (drawGameSky) tells whether any of it was seen; after a frame,
// cloudStep waits for that answer and draws the next frame only if some sky showed, so
// the loop runs at up to 30 frames a second while the sky is in view and stops when it
// isn't. Any other redraw (the camera moving, a click) asks again. An answer about an
// older view than the last frame drawn is asked again too. Without queries (an old
// driver) the clouds just keep moving.
const SKYQ={q:null,wait:false,seen:true,at:0};   // at: the frame the last question was asked in
let cloudTimer=0, FRAMES=0;
function skyQueryPoll(){
  if(!SKYQ.wait)return;
  try{if(gl.getQueryParameter(SKYQ.q,gl.QUERY_RESULT_AVAILABLE)){SKYQ.seen=!!gl.getQueryParameter(SKYQ.q,gl.QUERY_RESULT);SKYQ.wait=false;}}
  catch(_e){SKYQ.wait=false;SKYQ.seen=true;}
}
function cloudsMoving(){return CLOUDS_MOVE&&!simpleSky&&!(hiddenMask&C_SKY)&&!fogOn();}
function cloudTick(){if(!cloudTimer&&cloudsMoving())cloudTimer=setTimeout(cloudStep,33);}
function cloudStep(){
  cloudTimer=0;
  if(!cloudsMoving())return;
  skyQueryPoll();
  if(SKYQ.wait){cloudTimer=setTimeout(cloudStep,33);return;}
  if(SKYQ.seen||SKYQ.at<FRAMES)requestDraw();
}
function arrayTex(w,h,n,data){
  const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D_ARRAY,t);
  gl.texImage3D(gl.TEXTURE_2D_ARRAY,0,gl.RGBA8,w,h,n,0,gl.RGBA,gl.UNSIGNED_BYTE,data);
  for(const[p,v]of[[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])
    gl.texParameteri(gl.TEXTURE_2D_ARRAY,p,v);
  return t;
}
// Which of the game's polygons are shown follows their .map face (or patch, terrain
// block, entity) through the filters and Hide.
function litUnitShown(u){
  if(u.f>=0)return !!faceVis[u.f];
  if(u.pi>=0){const p=SC.prims[u.pi];for(let f=p.f0;f<p.f1;f++)if(faceVis[f])return true;return false;}
  if(hidEnt.has(u.ei))return false;
  const te=TEX[u.ti]||{f:0};
  let cat=WORLDLIKE[MAP.ents[u.ei].cls]?C_WORLD:C_ENTBRUSH;
  if(te.f&TF_SKY)cat|=C_SKY;if(te.f&(TF_BLEND|TF_ADD))cat|=C_TRANS;if(te.g==='liquid'||te.g==='fog')cat|=C_LIQUID;
  return !(cat&hiddenMask);
}
function rebuildLit(){
  const tri=new Uint32Array(LIT.tri.length);let n=0;
  LIT.ops=[];LIT.trans=[];LIT.sky=[];
  cullPrepLit();
  for(const[ti,list]of LIT.byTex){
    const start=n,sg=cullSegs();
    for(const k of list){const u=LIT.units[k];if(!litUnitShown(u))continue;sg.add(CULL.uk[k],CULL.ub,k*6,n,u.n);tri.set(LIT.tri.subarray(u.i0,u.i0+u.n),n);n+=u.n;}
    if(n===start)continue;
    const te=TEX[ti]||{f:0}, m=(MAT[ti]&&MAT[ti].lit)||{kind:0,af:0,alpha:1}, op={ti:ti,start:start,count:n-start,m:m,seg:sg.done()};
    if(te.f&TF_SKY)LIT.sky.push(op);else(m.kind>=2?LIT.trans:LIT.ops).push(op);
  }
  // those that write depth in game first (they hide what is behind them), then by kind
  const ord={4:0,5:1,2:2,3:3};
  LIT.trans.sort((a,b)=>((b.m.dw?1:0)-(a.m.dw?1:0))||(ord[a.m.kind]-ord[b.m.kind]));
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.lTri);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,tri.subarray(0,Math.max(3,n)),gl.DYNAMIC_DRAW);
}
function skyColour(){
  const wk=MAP.ents[0]?MAP.ents[0].kvl:{};
  return parseVec(wk.farplane_color,3)||TH.bg;
}

// ============================================================================
//  Camera
// ============================================================================
function camAxes(){
  const D2=Math.PI/180, cp=Math.cos(cam.pitch*D2),sp=Math.sin(cam.pitch*D2),cy=Math.cos(cam.yaw*D2),sy=Math.sin(cam.yaw*D2);
  const f=[cp*cy,cp*sy,-sp], r0=[sy,-cy,0], u0=vcross(r0,f);
  const cr=Math.cos(cam.roll*D2), sr=Math.sin(cam.roll*D2);
  const r=[r0[0]*cr+u0[0]*sr,r0[1]*cr+u0[1]*sr,r0[2]*cr+u0[2]*sr], u=[u0[0]*cr-r0[0]*sr,u0[1]*cr-r0[1]*sr,u0[2]*cr-r0[2]*sr];
  return{f:f,r:r,u:u};
}
let VP=null, NEAR=4, FAR=131072;
function farPlane(){
  let far=FAR;
  if(fogOn())far=fogFar()*1.02;
  if(clipOn)far=Math.min(far,clipDist*1.8);
  return far;
}
function viewProj(pick){
  const a=camAxes(), e=cam.pos;
  const V=[a.r[0],a.u[0],-a.f[0],0, a.r[1],a.u[1],-a.f[1],0, a.r[2],a.u[2],-a.f[2],0,
           -vdot(a.r,e),-vdot(a.u,e),vdot(a.f,e),1];
  const tx=Math.tan(fovX*Math.PI/360), ty=tx*H/W, n=NEAR, fz=farPlane();
  const Pm=[1/tx,0,0,0, 0,1/ty,0,0, 0,0,-(fz+n)/(fz-n),-1, 0,0,-2*fz*n/(fz-n),0];
  let M=mul4(Pm,V);
  if(pick){const cx=(pick[0]+0.5)/W*2-1, cy=1-(pick[1]+0.5)/H*2;
    const Z=[W,0,0,0, 0,H,0,0, 0,0,1,0, -cx*W,-cy*H,0,1];M=mul4(Z,M);}
  return new Float32Array(M);
}
function mul4(A,B2){const R=new Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++){let s=0;for(let k=0;k<4;k++)s+=A[k*4+r]*B2[c*4+k];R[c*4+r]=s;}return R;}
// world -> screen pixels (css), or null behind the camera
function project(p){
  const a=camAxes(), d=[p[0]-cam.pos[0],p[1]-cam.pos[1],p[2]-cam.pos[2]];
  const z=vdot(d,a.f); if(z<NEAR)return null;
  const tx=Math.tan(fovX*Math.PI/360), ty=tx*H/W;
  return [W/2+vdot(d,a.r)/(z*tx)*W/2, H/2-vdot(d,a.u)/(z*ty)*H/2, z];
}
function screenRay(x,y){
  const a=camAxes(), tx=Math.tan(fovX*Math.PI/360), ty=tx*H/W;
  const sx=(x/W*2-1)*tx, sy=(1-y/H*2)*ty;
  return vnorm([a.f[0]+a.r[0]*sx+a.u[0]*sy,a.f[1]+a.r[1]*sx+a.u[1]*sy,a.f[2]+a.r[2]*sx+a.u[2]*sy]);
}

// ============================================================================
//  Drawing
// ============================================================================
const FOG={far:0,col:[0.5,0.5,0.5]};
// The fog the game draws: the map's farplane, or r_farplane's in its place with its own
// colour (R_SetupFrustum); none with r_farplane_nofog (RB_SetupFog). The game always draws
// a farplane's fog, so r_farplane turns it on here whatever the Fog switch says.
function farOverride(){return !!Math.trunc(CVARS.r_farplane);}
function fogFar(){return farOverride()?CVARS.r_farplane:FOG.far;}
function fogCol(){return farOverride()?(parseVec(CVARS.r_farplane_color,3)||[0.5,0.5,0.5]):THU.flash?[0.9,0.9,0.9]:FOG.col;}
function fogOn(){return (view.fog||farOverride())&&fogFar()>0&&!CVARS.r_farplane_nofog;}
let _drawReq=false;
// A draw is asked for here and made once, by the frame loop (loop), however many things
// asked for it this frame (a mouse look, a key move, the clouds, the hover outline).
function requestDraw(){_drawReq=true;}
function resize(){const r=glcv.getBoundingClientRect();W=Math.max(1,r.width);H=Math.max(1,r.height);DPR=Math.min(2,window.devicePixelRatio||1);
  glcv.width=Math.round(W*DPR);glcv.height=Math.round(H*DPR);cv2.width=Math.round(W*DPR);cv2.height=Math.round(H*DPR);
  ctx.setTransform(DPR,0,0,DPR,0,0);requestDraw();}
window.addEventListener('resize',resize);

function setCommon(p,vp,mode){
  gl.useProgram(p);gl.uniformMatrix4fv(p.u.uVP,false,vp);gl.uniform1i(p.u.uMode,mode);
  gl.uniform1f(p.u.uShade,view.shade?1:0);gl.uniform3fv(p.u.uEye,cam.pos);gl.uniform1f(p.u.uClip,clipOn?clipDist:0);
  const ff=fogFar();gl.uniform3fv(p.u.uFogCol,fogCol());gl.uniform3f(p.u.uFog,ff*0.25,ff,(fogOn()&&mode===0)?1:0);
  gl.uniform4f(p.u.uTint,1,1,1,1);gl.uniform1i(p.u.uAF,0);gl.uniform1i(p.u.uUseTex,1);gl.uniform1i(p.u.uTex,0);
  if(p.u.uPush)gl.uniform1f(p.u.uPush,0);
  if(p.u.uTm){gl.uniform2f(p.u.uTm,1,1);gl.uniform1i(p.u.uAg,0);}
  gl.activeTexture(gl.TEXTURE0);
}
// game: drawing the game's own polygons (its picture and material where they differ)
function bindMat(p,ti,mode,game){
  const m=(game&&MAT[ti]?MAT[ti].lit:MAT[ti])||{kind:0,af:0,alpha:1}, te=TEX[ti]||{c:[0.5,0.5,0.5]};
  if(p===PM){const dv=te.dv;
    if(dv){gl.uniform4f(PM.u.uDv,dv[0],dv[1],dv[7],dv[8]);gl.uniform4f(PM.u.uDw,dv[3],dv[4],dv[5],dv[6]);gl.uniform1i(PM.u.uDf,dv[2]|0);}
    else gl.uniform4f(PM.u.uDv,0,0,0,1);}
  gl.bindTexture(gl.TEXTURE_2D,(game&&GLTG[ti])||GLT[ti]||whiteTex);
  gl.uniform1i(p.u.uUseTex,(view.tex||mode===1)?1:0);
  gl.uniform3fv(p.u.uFlat,te.c||[0.5,0.5,0.5]);
  gl.uniform1i(p.u.uAF,m.af&&(view.tex||mode===1)?m.af:0);
  if(mode===0)gl.uniform4f(p.u.uTint,1,1,1,m.kind===4?m.alpha:1);
  if(m.two||mode===1)gl.disable(gl.CULL_FACE);else gl.enable(gl.CULL_FACE);
  if(game&&p.u.uTm){const tm=m.tm||[1,1],q=m.agp||[1,0,0,1];
    gl.uniform2f(p.u.uTm,tm[0],tm[1]);gl.uniform1i(p.u.uAg,m.agk|0);gl.uniform4f(p.u.uAgP,q[0],q[1],q[2],q[3]);}
  if(game&&p.u.uLMOnly)gl.uniform1i(p.u.uLMOnly,CVARS.r_lightmap&&lmOnly(ti)?1:0);
}
function blendFor(kind){
  if(kind===3){gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);}
  else if(kind===5){gl.enable(gl.BLEND);gl.blendFunc(gl.DST_COLOR,gl.ZERO);}
  else if(kind===2||kind===4){gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);}
  else gl.disable(gl.BLEND);
}
// Everything pickable, in one pass. mode 0 = normal, 1 = pick ids (2 = only the sky
// faces' ids, see pickAt). Picking always uses the .map's faces; with the game's
// lighting on, the picture uses the game's polygons for every face it draws itself (op.rep).
function bindLit(p){
  // with a light turned off, the relit pages (LT); r_lightmap 2 always shows the baked bytes
  const t=CVARS.r_lightmap===2?(lmHeat()||B.lmTex):(LT.active?LT.lmOut:B.lmTex);
  gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D_ARRAY,t);gl.activeTexture(gl.TEXTURE0);
  gl.uniform1i(p.u.uLM,1);
  if(p.u.uVROn){gl.uniform1i(p.u.uVROn,LT.active?1:0);
    if(LT.active){gl.activeTexture(gl.TEXTURE6);gl.bindTexture(gl.TEXTURE_2D,LT.pOut);gl.activeTexture(gl.TEXTURE0);gl.uniform1i(p.u.uVR,6);}}
}
function setModelCommon(vp,mode,lit){
  setCommon(PM,vp,mode);
  dvUniforms();
  gl.activeTexture(gl.TEXTURE3);gl.bindTexture(gl.TEXTURE_2D,(LT.active?LT.pOut:B.smTex)||whiteTex);gl.activeTexture(gl.TEXTURE0);
  gl.uniform1i(PM.u.uStatic,3);gl.uniform1i(PM.u.uLit,0);gl.uniform1i(PM.u.uRel,LT.active?1:0);
  gl.uniform1i(PM.u.uAuto2,0);gl.uniform3fv(PM.u.uFwd,camAxes().f);
  if(lit)gl.uniform1f(PM.u.uShade,0);
}
function drawScene(vp,mode){
  FR=frustumOf(vp);
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);gl.frontFace(gl.CW);gl.cullFace(gl.BACK);
  if(mode===2){   // pick ids of the sky faces alone, at their own depth (pickAt)
    setCommon(PW,vp,1);gl.bindVertexArray(B.vTri);gl.disable(gl.BLEND);
    for(const op of drawOps)if(op.sky){bindMat(PW,op.ti,1);drawRuns(op);}
    gl.bindVertexArray(null);return;
  }
  const lit=mode===0&&litOn();
  // world: solid first. Caulk is pushed back half a unit so it never pokes through
  // where a wall meets the caulked end of the next brush (sparkles along corners).
  // The sky faces are drawn here only with Simple Sky (MOHRadiant's tiled sky); otherwise
  // the game's sky is drawn behind everything (drawGameSky).
  const gameSky=!simpleSky;
  setCommon(PW,vp,mode);gl.bindVertexArray(B.vTri);gl.disable(gl.BLEND);
  for(const op of drawOps){if(op.sky?gameSky:(lit&&op.rep))continue;bindMat(PW,op.ti,mode);gl.uniform1f(PW.u.uPush,op.back?0.5:0);
    drawRuns(op);}
  gl.uniform1f(PW.u.uPush,0);
  if(lit){
    setCommon(PLIT,vp,0);bindLit(PLIT);gl.bindVertexArray(B.vLit);
    for(const op of LIT.ops){bindMat(PLIT,op.ti,0,true);drawRuns(op);}
  }
  if(gameSky&&mode===0&&!THU.flash)drawGameSky(vp);
  // models (solid surfaces)
  setModelCommon(vp,mode,lit);
  for(const R of modelsDrawn(mode)){if(!R.n)continue;gl.bindVertexArray(R.vao);
    for(const s of R.surfs){if(!surfOn(R,s))continue;const k=(MAT[s.ti]||{}).kind||0;if(mode===0&&k>=2)continue;
      if(lit)gl.uniform1i(PM.u.uLit,modelLitMode(s.ti));
      gl.uniform1i(PM.u.uAuto2,s.lod?1:0);
      bindMat(PM,s.ti,mode);gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.n);}}
  gl.uniform1i(PM.u.uAuto2,0);
  // entity markers
  if(boxCount){setCommon(PMK,vp,mode);gl.uniform1f(PMK.u.uOlW,3*DPR);
    gl.enable(gl.CULL_FACE);gl.bindVertexArray(B.vMark);gl.drawElements(gl.TRIANGLES,boxCount,gl.UNSIGNED_INT,0);}
  if(mode===1){
    drawSprites(vp,1);
    // see-through world surfaces are pickable too (that is how you find a trigger)
    setCommon(PW,vp,1);gl.bindVertexArray(B.vTri);
    for(const op of drawTrans){bindMat(PW,op.ti,1);drawRuns(op);}
    // the game's sky can be picked only where nothing else is, as it is seen
    if(gameSky){gl.depthRange(1,1);
      for(const op of drawOps)if(op.sky){bindMat(PW,op.ti,1);drawRuns(op);}
      gl.depthRange(0,1);}
    // the level script's trigger volumes, as the map's trigger brushes (Script trigs)
    pickScriptTrigs(vp);
    gl.bindVertexArray(null);return;
  }
  // See-through surfaces, in layers: the game's own (water, glass, glows; a blended
  // stage with depthWrite writes depth here too, as the beach's surf does in game),
  // then the models', then the editor's volumes (triggers, clips, hints...) over all of
  // them, so water can't paint over a trigger that is above it.
  gl.depthMask(false);
  if(lit&&LIT.trans.length){
    setCommon(PLIT,vp,0);bindLit(PLIT);gl.bindVertexArray(B.vLit);
    for(const op of LIT.trans){gl.depthMask(!!op.m.dw);blendFor(op.m.kind);bindMat(PLIT,op.ti,0,true);
      drawRuns(op);}
    gl.depthMask(false);
  }
  drawDecals(vp,lit);
  setCommon(PW,vp,0);gl.bindVertexArray(B.vTri);
  for(const op of drawTransG){if(lit&&op.rep)continue;blendFor(op.m.kind);bindMat(PW,op.ti,0);drawRuns(op);}
  setModelCommon(vp,0,lit);
  for(const R of modelsDrawn(0)){if(!R.n)continue;gl.bindVertexArray(R.vao);
    for(const s of R.surfs){if(!surfOn(R,s))continue;const k=(MAT[s.ti]||{}).kind||0;if(k<2)continue;
      if(lit)gl.uniform1i(PM.u.uLit,modelLitMode(s.ti));
      gl.uniform1i(PM.u.uAuto2,s.lod?1:0);
      blendFor(k);bindMat(PM,s.ti,0);gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.n);}}
  gl.uniform1i(PM.u.uAuto2,0);
  setCommon(PW,vp,0);gl.bindVertexArray(B.vTri);
  for(const op of drawTransE){if(lit&&op.rep)continue;blendFor(op.m.kind);bindMat(PW,op.ti,0);drawRuns(op);}
  // the inner sides of see-through brushes the camera is inside
  if(insideOps.length){gl.bindVertexArray(B.vInside);
    for(const op of insideOps){blendFor(4);bindMat(PW,op.ti,0);gl.enable(gl.CULL_FACE);gl.cullFace(gl.FRONT);
      drawRuns(op);}
    gl.cullFace(gl.BACK);}
  drawSprites(vp);
  drawWeather(vp);
  gl.depthMask(true);gl.disable(gl.BLEND);gl.bindVertexArray(null);
}
// The game's sky (Simple Sky off): the sky box in the direction of each pixel of the
// sky polygons (a .bsp's own, else the .map's sky faces), or the fog / backdrop colour,
// with the shader's cloud layers over it. Drawn at the far end of the depth range as
// RB_StageIteratorSky does, so it only shows where nothing else was drawn: a building
// behind a sky brush is seen through it. With the map's fog on there are no clouds: the
// fog covers the whole sky.
function drawGameSky(vp){
  const ops=LIT?LIT.sky:drawOps.filter(op=>op.sky);
  const fogged=fogOn(), flat=fogged?fogCol():skyColour(), T=(performance.now()-T0)/1000;
  const cloudsOf=op=>{const te=TEX[op.ti]||{};return(!fogged&&te.cl!=null)?CLOUDS[te.cl]:null;};
  // the skies with moving clouds go last, inside an occlusion query: is any of them seen?
  // (see cloudStep). A sky with still clouds, or none, doesn't keep the view redrawing.
  const still=[], moving=[];
  for(const op of ops){const C=cloudsOf(op);(C&&C.mv?moving:still).push(op);}
  if(!moving.length&&!SKYQ.wait){SKYQ.seen=false;SKYQ.at=FRAMES;}
  if(!ops.length)return;
  gl.bindVertexArray(LIT?B.vLit:B.vTri);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
  gl.depthRange(1,1);
  let P=null;
  const drawOne=op=>{
    const te=TEX[op.ti]||{}, sb=te.sb, t=(!fogged&&sb!=null)?B.skyTex[sb]:null;
    const C=cloudsOf(op), list=cloudLayers(C), Q=skyProgram(list.length);
    if(Q!==P){P=Q;gl.useProgram(P);gl.uniformMatrix4fv(P.u.uVP,false,vp);gl.uniform3fv(P.u.uEye,cam.pos);
      gl.uniform1f(P.u.uClip,clipOn?clipDist:0);gl.uniform1i(P.u.uSky,2);gl.uniform3fv(P.u.uSkyCol,flat);
      for(let k=0;k<4;k++)if(P.u['uC'+k])gl.uniform1i(P.u['uC'+k],4+k);
      if(P.u.uPush)gl.uniform1f(P.u.uPush,0);}
    gl.activeTexture(gl.TEXTURE2);gl.bindTexture(gl.TEXTURE_2D_ARRAY,t||B.skyNone);gl.activeTexture(gl.TEXTURE0);
    gl.uniform1i(P.u.uHasBox,t?1:0);
    if(list.length)setClouds(P,C,list,T);
    gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);};
  still.forEach(drawOne);
  let query=false;
  if(moving.length&&!SKYQ.wait){
    try{if(!SKYQ.q)SKYQ.q=gl.createQuery();gl.beginQuery(gl.ANY_SAMPLES_PASSED,SKYQ.q);query=true;SKYQ.at=FRAMES;}catch(_e){}}
  moving.forEach(drawOne);
  if(query){gl.endQuery(gl.ANY_SAMPLES_PASSED);SKYQ.wait=true;}
  gl.depthRange(0,1);
}
// mode 1: the pick pass (an entity drawn only by its sprites, a fire, can be clicked)
function drawSprites(vp,mode){
  const P=[],T=[],K=[],ops=[];const a=camAxes();
  for(const R of MODELS){if(!R.sprites.length)continue;
    for(const ei of R.inst){if(!entShown(ei))continue;const rows=instRows(ENTS[ei]);
      for(const s of R.sprites){
        const c=[rows[0]*s.c[0]+rows[1]*s.c[1]+rows[2]*s.c[2]+rows[3],rows[4]*s.c[0]+rows[5]*s.c[1]+rows[6]*s.c[2]+rows[7],rows[8]*s.c[0]+rows[9]*s.c[1]+rows[10]*s.c[2]+rows[11]];
        const sc=Math.hypot(rows[0],rows[4],rows[8])||1, r=s.r*sc*0.75;
        const st=P.length/3;
        const q=[[-1,-1,0,1],[1,-1,1,1],[1,1,1,0],[-1,1,0,0]];
        for(const v of [q[0],q[1],q[2],q[0],q[2],q[3]]){P.push(c[0]+(a.r[0]*v[0]+a.u[0]*v[1])*r,c[1]+(a.r[1]*v[0]+a.u[1]*v[1])*r,c[2]+(a.r[2]*v[0]+a.u[2]*v[1])*r);T.push(v[2],v[3]);K.push(NF+1+ei);}
        ops.push([s.ti,st,6]);}}}
  if(!ops.length)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,B.spP);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(P),gl.STREAM_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.spT);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(T),gl.STREAM_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.spK);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(K),gl.STREAM_DRAW);
  setCommon(PW,vp,mode?1:0);gl.bindVertexArray(B.vSp);gl.disable(gl.CULL_FACE);
  if(mode){gl.disable(gl.BLEND);for(const op of ops){bindMat(PW,op[0],1);gl.drawArrays(gl.TRIANGLES,op[1],op[2]);}gl.bindVertexArray(null);return;}
  for(const op of ops){const k=(MAT[op[0]]||{}).kind||0;blendFor(k===0?3:k);bindMat(PW,op[0],0);gl.disable(gl.CULL_FACE);gl.drawArrays(gl.TRIANGLES,op[1],op[2]);}
}
// ---- the map's permanent decals (Decals, =) -----------------------------------------------
// D.dcl: the fragments of maps/<map>.dcl (R_LoadPermanentMarks, tr_marks_permanent.c),
// each a fan of up to 8 vertices with its shader and the colour the game lit it with
// (rgbGen / alphaGen vertex). Drawn after the solid world and models, blended, pushed
// toward the camera (the decal shaders' polygonOffset) and without writing depth. With
// the game's lighting off (Full Brightness, a .map) the colour is white and only the
// alpha is kept. Not pickable: a click goes to the wall under the decal.
const VS_DCL=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV; layout(location=7) in vec4 aCol;
uniform mat4 uVP; uniform int uWhite;
out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
void main(){vUV=aUV;vPos=aPos;vCol=uWhite==1?vec4(1.0,1.0,1.0,aCol.a):aCol;vPick=0.0;gl_Position=uVP*vec4(aPos,1.0);}`;
const DCL={P:null,vao:null,ops:[],n:0};
function dclHas(){return !!(D&&D.dcl&&!D.dcl.err&&D.dcl.nf>0);}
function dclWhy(){
  if(!D||!D.dcl)return 'This map has no decals: no '+(D&&D.name||'map')+'.dcl in the paks or beside the file.';
  if(D.dcl.err)return 'The decals '+D.dcl.src+' can\'t be read: '+D.dcl.err;
  return 'The map\'s .dcl ('+D.dcl.src+') has no decals.';}
function dclGL(){
  if(!dclHas())return;
  const G=D.dcl,T=D.i32(G.t),K=D.i32(G.k),P=D.f32(G.p),S=D.f32(G.s),C=D.bytes(G.c);
  // triangle fans into one list, grouped by texture
  const by=new Map();let v=0;
  for(let f=0;f<T.length;f++){const n=K[f];if(!by.has(T[f]))by.set(T[f],[]);
    const L=by.get(T[f]);for(let k=1;k+1<n;k++)L.push(v,v+k,v+k+1);v+=n;}
  const pos=[],uv=[],col=[];DCL.ops=[];
  for(const[ti,L]of by){const first=pos.length/3;
    for(const i of L){pos.push(P[i*3],P[i*3+1],P[i*3+2]);uv.push(S[i*2],S[i*2+1]);col.push(C[i*4],C[i*4+1],C[i*4+2],C[i*4+3]);}
    DCL.ops.push([ti,first,L.length]);}
  DCL.n=pos.length/3;
  DCL.P=compile(VS_DCL,FS_MAIN);
  DCL.vao=gl.createVertexArray();gl.bindVertexArray(DCL.vao);
  attr(0,makeBuf(gl.ARRAY_BUFFER,new Float32Array(pos)),3);attr(1,makeBuf(gl.ARRAY_BUFFER,new Float32Array(uv)),2);
  gl.bindBuffer(gl.ARRAY_BUFFER,makeBuf(gl.ARRAY_BUFFER,new Uint8Array(col)));gl.enableVertexAttribArray(7);
  gl.vertexAttribPointer(7,4,gl.UNSIGNED_BYTE,true,0,0);
  gl.bindVertexArray(null);
}
function drawDecals(vp,lit){
  if(!view.decals||!DCL.n)return;
  const P=DCL.P;setCommon(P,vp,0);gl.uniform1f(P.u.uShade,0);gl.uniform1i(P.u.uWhite,lit?0:1);
  gl.bindVertexArray(DCL.vao);gl.depthMask(false);
  gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(-1,-2);
  for(const[ti,first,count]of DCL.ops){const k=(MAT[ti]||{}).kind||0;
    bindMat(P,ti,0);gl.disable(gl.CULL_FACE);gl.uniform4f(P.u.uTint,1,1,1,1);blendFor(k===0||k===4?2:k);
    gl.drawArrays(gl.TRIANGLES,first,count);}
  gl.disable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(0,0);gl.bindVertexArray(null);
}

// ---- the leak trail (Leak, P) ---------------------------------------------------------------
// D.leak: maps/<map>.lin, the line q3map writes when the void outside the map reaches an
// entity (LeakFile in the compiler: from the outside node, the middle of each portal on
// the shortest way in, then the origin of the entity it reached). The first point is
// therefore in the opening the void comes in through: that is where the map isn't sealed.
// Drawn over everything, so it shows through walls.
function leakHas(){return !!(D&&D.leak&&D.leak.p&&D.leak.p.length>=2);}
function leakWhy(){
  if(!D||!D.leak)return 'No leak trail: there is no '+(D&&D.name||'map')+'.lin in the paks or beside the file (the compiler writes one only when the map leaks).';
  return 'The leak trail '+D.leak.src+' can\'t be used: '+(D.leak.err||'it has fewer than 2 points');}
let LEAKENT=undefined;
// the entity the trail ends at: its origin is the last point (GetVectorForKey "origin")
function leakEnt(){
  if(LEAKENT!==undefined)return LEAKENT;
  const p=D.leak.p[D.leak.p.length-1];LEAKENT=-1;
  for(let ei=1;ei<MAP.ents.length;ei++){const o=parseVec(MAP.ents[ei].kvl.origin,3);
    if(o&&Math.abs(o[0]-p[0])<0.6&&Math.abs(o[1]-p[1])<0.6&&Math.abs(o[2]-p[2])<0.6){LEAKENT=ei;break;}}
  return LEAKENT;
}
// ---- where the void gets in --------------------------------------------------------------
// The brushes that seal a map for the compiler: the world's (func_group's too) structural
// brushes that are solid and not see-through. Detail brushes, patches, terrain, clips,
// water and "surfaceparm trans" brushes don't: the compiler's flood goes through them.
let LEAKSEAL=null,LEAKFIX=undefined,LEAKSEL=-1;
function leakSeal(){
  if(LEAKSEAL)return LEAKSEAL;
  const L=[];
  for(let pi=0;pi<SC.prims.length;pi++){const p=SC.prims[pi];
    if(p.kind!==0||!isFinite(p.mins[0]))continue;
    const e=MAP.ents[p.ent];if(!WORLDLIKE[e.cls]||e.cls==='detail'||e.cls==='func_detail')continue;
    const pr=e.prims[p.bn];if(!pr||!pr.d||!pr.d.faces.length)continue;
    const F=pr.d.faces,bc=pgBcont(p.ent,p.bn);
    if((bc!=null&&(bc&CONTENTS_DETAIL))||F.some(f=>(f.cont|0)&CONTENTS_DETAIL))continue;
    let c=0;for(const f of F){const te=texFor(f.tex);c|=pgCont(bc!=null?bc:f.cont,te);if((te.p||[]).includes('trans'))c|=CONTENTS_TRANSLUCENT;}
    if(bc!=null)c|=bc&CONTENTS_TRANSLUCENT;
    if(!(c&1)||(c&CONTENTS_TRANSLUCENT))continue;
    const pl=[];for(const f of F){const q=planeOf(f);if(q)pl.push(q);}
    if(pl.length>=4)L.push({mn:p.mins,mx:p.maxs,pl:pl,pi:pi});}
  return LEAKSEAL=L;
}
// ---- labels through walls ---------------------------------------------------------------
// The world brushes that hide a label behind them: solid, not see-through (no
// "surfaceparm trans", not water), detail ones included, and only while one of their
// faces is shown (World / Details / Caulk off, Hide). Patches, terrain and brush
// entities don't hide labels. A box tree (BVH) over them keeps a sight line cheap.
let LBLOCC=null;
function lblOccluders(){
  if(!LBLOCC){
    const L=[];
    for(let pi=0;pi<SC.prims.length;pi++){const p=SC.prims[pi];
      if(p.kind!==0||!isFinite(p.mins[0]))continue;
      const e=MAP.ents[p.ent];if(!WORLDLIKE[e.cls])continue;
      const pr=e.prims[p.bn];if(!pr||!pr.d||!pr.d.faces.length)continue;
      const F=pr.d.faces,bc=pgBcont(p.ent,p.bn);
      let c=0;for(const f of F){const te=texFor(f.tex);c|=pgCont(bc!=null?bc:f.cont,te);if((te.p||[]).includes('trans'))c|=CONTENTS_TRANSLUCENT;}
      if(bc!=null)c|=bc&CONTENTS_TRANSLUCENT;
      if(!(c&1)||(c&CONTENTS_TRANSLUCENT))continue;
      const pl=[];for(const f of F){const q=planeOf(f);if(q)pl.push(q);}
      if(pl.length>=4)L.push({mn:p.mins,mx:p.maxs,pl:pl,p:p,on:true});}
    const build=(it)=>{const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
      for(const B of it)for(let k=0;k<3;k++){if(B.mn[k]<mn[k])mn[k]=B.mn[k];if(B.mx[k]>mx[k])mx[k]=B.mx[k];}
      if(it.length<=4)return{mn:mn,mx:mx,it:it};
      let ax=0;for(let k=1;k<3;k++)if(mx[k]-mn[k]>mx[ax]-mn[ax])ax=k;
      it.sort((a,b)=>(a.mn[ax]+a.mx[ax])-(b.mn[ax]+b.mx[ax]));const h=it.length>>1;
      return{mn:mn,mx:mx,l:build(it.slice(0,h)),r:build(it.slice(h))};};
    LBLOCC={L:L,root:L.length?build(L.slice()):null,key:''};
  }
  // which of them are shown, again when the Show buttons or Hide change
  const key=hiddenMask+':'+hidPrim.size+':'+hidEnt.size+':'+EXP.hid.size+':'+(THU.hid?1:0);
  if(LBLOCC.key!==key){LBLOCC.key=key;
    for(const B of LBLOCC.L){let on=false;for(let f=B.p.f0;f<B.p.f1&&!on;f++)if(faceShown(f))on=true;B.on=on;}}
  return LBLOCC;
}
// Does a shown occluder stand between a and b? (the last 2 units before b don't count,
// so a label on a floor or a wall isn't hidden by the brush it sits on)
function lblBlocked(a,b){
  const O=lblOccluders();if(!O.root)return false;
  const d=[b[0]-a[0],b[1]-a[1],b[2]-a[2]],len=Math.hypot(d[0],d[1],d[2]);if(len<1)return false;
  const tEnd=1-2/len,st=[O.root];
  const slab=(mn,mx)=>{let t0=0,t1=tEnd;
    for(let k=0;k<3;k++){if(Math.abs(d[k])<1e-9){if(a[k]<mn[k]||a[k]>mx[k])return false;continue;}
      let u=(mn[k]-a[k])/d[k],v=(mx[k]-a[k])/d[k];if(u>v){const w=u;u=v;v=w;}if(u>t0)t0=u;if(v<t1)t1=v;if(t0>t1)return false;}
    return true;};
  while(st.length){const N=st.pop();if(!slab(N.mn,N.mx))continue;
    if(N.l){st.push(N.l,N.r);continue;}
    for(const B of N.it){if(!B.on)continue;
      let t0=0,t1=tEnd,ok=true;
      for(const q of B.pl){const dn=q[0]*d[0]+q[1]*d[1]+q[2]*d[2],dist=q[0]*a[0]+q[1]*a[1]+q[2]*a[2]-q[3];
        if(Math.abs(dn)<1e-9){if(dist>0){ok=false;break;}continue;}
        const t=-dist/dn;if(dn<0){if(t>t0)t0=t;}else if(t<t1)t1=t;
        if(t0>t1){ok=false;break;}}
      if(ok&&t0<t1)return true;}}
  return false;
}
// sight lines kept until the camera moves (a 4-unit step) or the Show buttons change
const LBLVIS={key:'',m:new Map()};
function lblSeen(ei,top){
  const k=Math.round(cam.pos[0]/4)+','+Math.round(cam.pos[1]/4)+','+Math.round(cam.pos[2]/4)+'|'+(LBLOCC?LBLOCC.key:'');
  if(LBLVIS.key!==k){LBLVIS.key=k;LBLVIS.m.clear();}
  let v=LBLVIS.m.get(ei);
  if(v===undefined){v=!lblBlocked(cam.pos,top);LBLVIS.m.set(ei,v);}
  return v;
}
// how far a ray goes before a sealing brush: [distance, brush] or null when it gets out
function leakRay(o,d,len){
  let best=len,hit=null;
  for(const B of leakSeal()){
    // the box first (slabs)
    let t0=0,t1=best;
    for(let k=0;k<3&&t0<=t1;k++){if(Math.abs(d[k])<1e-9){if(o[k]<B.mn[k]-0.01||o[k]>B.mx[k]+0.01)t0=Infinity;continue;}
      let a=(B.mn[k]-0.01-o[k])/d[k],b=(B.mx[k]+0.01-o[k])/d[k];if(a>b){const x=a;a=b;b=x;}if(a>t0)t0=a;if(b<t1)t1=b;}
    if(t0>t1)continue;
    t0=0;t1=best;
    for(const q of B.pl){const dn=q[0]*d[0]+q[1]*d[1]+q[2]*d[2],dist=q[0]*o[0]+q[1]*o[1]+q[2]*o[2]-q[3];
      if(Math.abs(dn)<1e-9){if(dist>0.01){t0=Infinity;break;}continue;}
      const t=-dist/dn;if(dn<0){if(t>t0)t0=t;}else if(t<t1)t1=t;
      if(t0>t1)break;}
    if(t0<=t1&&t0<best){best=t0;hit=B;}}
  return hit?[best,hit]:null;
}
const LEAK_DIRS=(()=>{const D=[];for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++)if(x||y||z)D.push(vnorm([x,y,z]));return D;})();
const LEAK_AX=[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
// the ways the void is in a straight line from a point (rays that leave the map's box
// without meeting a sealing brush)
function leakOut(p,len){const r=[];for(const d of LEAK_DIRS)if(!leakRay(p,d,len))r.push(d);return r;}
// Along the trail from its start: the last place the void is still in sight, before the
// trail is shut in by sealing brushes. That is where it comes through the map's shell: the
// gap to close. Its size is measured there along the three axes.
function leakFix(){
  if(LEAKFIX!==undefined)return LEAKFIX;
  LEAKFIX=null;
  const t0=performance.now(),P=D.leak.p,w=worldBounds(),len=Math.hypot(w.maxs[0]-w.mins[0],w.maxs[1]-w.mins[1],w.maxs[2]-w.mins[2])+512;
  const S=[];                         // samples: [point, trail point index before it]
  for(let i=0;i<P.length-1;i++){const a=P[i],b=P[i+1],l=Math.hypot(b[0]-a[0],b[1]-a[1],b[2]-a[2]),n=Math.max(1,Math.min(64,Math.ceil(l/32)));
    for(let k=0;k<n;k++)S.push([[a[0]+(b[0]-a[0])*k/n,a[1]+(b[1]-a[1])*k/n,a[2]+(b[2]-a[2])*k/n],i]);}
  S.push([P[P.length-1].slice(),P.length-1]);
  let last=-1,first=-1;
  for(let j=0;j<S.length;j++){const o=leakOut(S[j][0],len);if(o.length){last=j;S[j].out=o;}else{first=j;break;}}
  const R={ms:0};
  if(last<0){R.ms=performance.now()-t0;return LEAKFIX=R;}  // shut in from the start: nothing to say
  // the void in sight from the entity too: it is out in the void itself when most ways
  // from it are open, else the gap is within its sight
  if(first<0&&S[last].out.length>=18)R.entOut=true;
  const sp=S[last][0];R.i=S[last][1];R.out=S[last].out;
  // the way(s) out, the axis ones first
  const ax=R.out.filter(d=>Math.abs(d[0])>0.99||Math.abs(d[1])>0.99||Math.abs(d[2])>0.99);
  R.dir=(ax.length?ax:R.out)[0];
  // The gap itself: from there toward the void, the last place the way out is still
  // between sealing brushes (a crack at once; the far edge of a missing wall further on)
  let fp=sp;
  // something the game collides with on the way out (terrain, a patch, a detail brush) that
  // the compiler doesn't take as a seal: the void comes in through that
  if(!R.entOut)try{const e=[sp[0]+R.dir[0]*len,sp[1]+R.dir[1]*len,sp[2]+R.dir[2]*len],t=pgTrace(sp,e,[0,0,0],[0,0,0],false);
    if(t&&t.f<1){const at=[0,1,2].map(k=>sp[k]+(e[k]-sp[k])*t.f);R.cover=Object.assign({at:at.map(v=>Math.round(v*100)/100),ent:t.ent},leakWhatAt(at,R.dir));}}catch(_e){}
  if(R.cover)fp=R.cover.at;
  else if(!R.entOut){
    const d=R.dir,lk=[0,1,2].map(k=>Math.abs(d[k])),along=lk.indexOf(Math.max(...lk));
    let tx=len;for(let k=0;k<3;k++){if(Math.abs(d[k])<1e-9)continue;const t=((d[k]>0?w.maxs[k]+64:w.mins[k]-64)-sp[k])/d[k];if(t>0&&t<tx)tx=t;}
    const st=Math.max(2,tx/600);const FL=[];
    for(let t=0;t<=tx;t+=st){const q=[sp[0]+d[0]*t,sp[1]+d[1]*t,sp[2]+d[2]*t];let c=Infinity;
      for(let k=0;k<3;k++){if(k===along)continue;const a=leakRay(q,LEAK_AX[k*2],1024),b=leakRay(q,LEAK_AX[k*2+1],1024);
        if(a&&b)c=Math.min(c,a[0]+b[0]);}
      // the last place still flanked by sealing brushes (across one of the two other axes,
      // within 1024 units): past it the way out is in the void, so that is the opening
      if(isFinite(c))FL.push([t,q,c]);}
    // the gap is measured at its narrowest within 64 units of that opening (its lip)
    if(FL.length){const tl=FL[FL.length-1][0];let b=null;for(const f of FL)if(f[0]>=tl-64&&(!b||f[2]<b[2]-0.01))b=f;fp=b[1];}
  }
  R.p=fp.map(v=>Math.round(v*100)/100);R.from=sp.map(v=>Math.round(v*100)/100);
  // the gap: the free space round the point along each axis, and the brushes either side
  R.ax=[0,1,2].map(k=>{const a=leakRay(fp,LEAK_AX[k*2],4096),b=leakRay(fp,LEAK_AX[k*2+1],4096);
    return{w:(a?a[0]:Infinity)+(b?b[0]:Infinity),lo:b?fp[k]-b[0]:null,hi:a?fp[k]+a[0]:null,pr:[b&&b[1].pi,a&&a[1].pi].filter(x=>x!=null)};});
  let nk=-1;for(let k=0;k<3;k++)if(isFinite(R.ax[k].w)&&(nk<0||R.ax[k].w<R.ax[nk].w))nk=k;
  R.nk=nk;
  // how much of the trail runs with the void in sight from its start
  R.run=0;for(let j=1;j<=last;j++)R.run+=Math.hypot(S[j][0][0]-S[j-1][0][0],S[j][0][1]-S[j-1][0][1],S[j][0][2]-S[j-1][0][2]);
  R.ms=performance.now()-t0;
  return LEAKFIX=R;
}
// what the game collides with at a point that doesn't seal the map: terrain, a patch, a
// detail brush, or a clip / see-through / liquid brush (and its prim, to select it)
function leakWhatAt(p,d){
  const q=[p[0]+d[0]*2,p[1]+d[1]*2,p[2]+d[2]*2];       // just inside it
  for(const ps of[q,p])for(let pi=0;pi<SC.prims.length;pi++){const P=SC.prims[pi];
    if(!isFinite(P.mins[0])||ps[0]<P.mins[0]-1||ps[0]>P.maxs[0]+1||ps[1]<P.mins[1]-1||ps[1]>P.maxs[1]+1||ps[2]<P.mins[2]-1||ps[2]>P.maxs[2]+1)continue;
    if(P.kind===2)return{kind:'terrain',pi:pi};
    if(P.kind===1)return{kind:'patch',pi:pi};
    const pr=MAP.ents[P.ent].prims[P.bn];if(!pr||!pr.d)continue;
    let inside=true;for(const f of pr.d.faces){const pl=planeOf(f);if(pl&&pl[0]*ps[0]+pl[1]*ps[1]+pl[2]*ps[2]-pl[3]>1){inside=false;break;}}
    if(!inside)continue;
    const bc=pgBcont(P.ent,P.bn),det=MAP.ents[P.ent].cls==='detail'||(bc!=null&&(bc&CONTENTS_DETAIL))||pr.d.faces.some(f=>(f.cont|0)&CONTENTS_DETAIL);
    if(det)return{kind:'detail brush',pi:pi};
    if(!WORLDLIKE[MAP.ents[P.ent].cls])return{kind:'brush entity',pi:pi};
    return{kind:'brush that doesn\'t seal (a clip, see-through or liquid)',pi:pi};}
  return{kind:'terrain, a patch or a detail brush'};
}
function leakDirName(d){
  const n=[];if(d[2]>0.5)n.push('above');if(d[2]<-0.5)n.push('below');
  const h=[];if(d[0]>0.5)h.push('+x');if(d[0]<-0.5)h.push('-x');if(d[1]>0.5)h.push('+y');if(d[1]<-0.5)h.push('-y');
  if(h.length)n.push('toward '+h.join(' '));return n.join(', ')||'out';
}
function leakLen(){const p=D.leak.p;let l=0;for(let i=1;i<p.length;i++)l+=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1],p[i][2]-p[i-1][2]);return l;}
function drawLeak2D(){
  if(!view.leak||!leakHas())return;
  const a=camAxes(), e=cam.pos, pts=D.leak.p;
  const depth=p=>(p[0]-e[0])*a.f[0]+(p[1]-e[1])*a.f[1]+(p[2]-e[2])*a.f[2];
  const segs=[];
  for(let i=1;i<pts.length;i++){let A=pts[i-1],Bq=pts[i],za=depth(A),zb=depth(Bq);const N=NEAR+0.5;
    if(za<N&&zb<N)continue;
    if(za<N){const t=(N-za)/(zb-za);A=[A[0]+(Bq[0]-A[0])*t,A[1]+(Bq[1]-A[1])*t,A[2]+(Bq[2]-A[2])*t];}
    else if(zb<N){const t=(N-zb)/(za-zb);Bq=[Bq[0]+(A[0]-Bq[0])*t,Bq[1]+(A[1]-Bq[1])*t,Bq[2]+(A[2]-Bq[2])*t];}
    const pa=project(A),pb=project(Bq);if(pa&&pb)segs.push([pa,pb]);}
  ctx.save();ctx.lineCap='round';ctx.lineJoin='round';
  for(const[w,c]of[[6,'rgba(0,0,0,.55)'],[3,'#ff3030']]){ctx.lineWidth=w;ctx.strokeStyle=c;ctx.beginPath();
    for(const[pa,pb]of segs){ctx.moveTo(pa[0],pa[1]);ctx.lineTo(pb[0],pb[1]);}ctx.stroke();}
  // the points along it, the hole and the entity marked
  ctx.fillStyle='#ffd040';
  for(let i=1;i<pts.length-1;i++){const s=project(pts[i]);if(s){ctx.beginPath();ctx.arc(s[0],s[1],3,0,Math.PI*2);ctx.fill();}}
  ctx.font='bold 11px ui-monospace,Menlo,Consolas,monospace';ctx.textBaseline='middle';
  const tag=(p,txt,col)=>{const s=project(p);if(!s)return;
    ctx.lineWidth=3;ctx.strokeStyle='rgba(0,0,0,.6)';ctx.beginPath();ctx.arc(s[0],s[1],9,0,Math.PI*2);ctx.stroke();
    ctx.lineWidth=2;ctx.strokeStyle=col;ctx.beginPath();ctx.arc(s[0],s[1],9,0,Math.PI*2);ctx.stroke();
    const tw=ctx.measureText(txt).width;ctx.fillStyle='rgba('+TH.labelbg+',.85)';ctx.fillRect(s[0]+13,s[1]-8,tw+8,16);
    ctx.fillStyle=col;ctx.fillText(txt,s[0]+17,s[1]);};
  const ei=leakEnt(),F=leakFix();
  tag(pts[pts.length-1],'leak: reaches '+(ei>0?(MAP.ents[ei].kvl.classname||'entity')+' (entity '+ei+')':'an entity'),'#ffd040');
  tag(pts[0],'leak: starts in the void','#ff3030');
  if(F&&F.p&&!F.entOut)tag(F.p,'leak: gets in here, fix this'+(F.nk>=0&&F.ax[F.nk].w<64?' ('+fnum(Math.round(F.ax[F.nk].w*10)/10)+'-unit gap)':''),'#40e0ff');
  if(LEAKSEL>=0&&pts[LEAKSEL]){const s=project(pts[LEAKSEL]);if(s){ctx.lineWidth=2;ctx.strokeStyle='#fff';ctx.beginPath();ctx.arc(s[0],s[1],6,0,Math.PI*2);ctx.stroke();}}
  ctx.restore();
}
function leakCard(){
  infoMode='leak';
  if(!leakHas()){card('Leak trail','<div class="note">'+esc(leakWhy())+'</div>');return;}
  // Go looks at a point from along the trail (the next point's side, the last one from the
  // one before it): the trail runs through open space, so the camera is never in a wall,
  // and at the hole it looks out through it from inside
  const L=D.leak,p=L.p,ei=leakEnt(),
    go=i=>{const q=p[i],f=p[i+1<p.length?i+1:i-1];
      return ' <button class="sm" data-go="'+q.join(' ')+'" data-from="'+f.join(' ')+'" title="Fly to it, looking along the trail">Go</button>'+copyBtn(fvec(q));};
  const F=leakFix(),ename=ei>0?linkEnt(ei):'an entity',pr=v=>esc(fvec(v));
  let h='<div><b>'+esc(L.src)+'</b>: '+p.length+' points, '+fnum(Math.round(leakLen()))+' units long</div>';
  // a .bsp that has vis was compiled sealed (a leaking compile leaves the vis out): the
  // .lin is from an earlier compile, found in another pak or beside the file
  if(D.kind==='bsp'&&GV&&GV.pvs)h+='<div class="warn">This .bsp has vis data, so the compile that made it didn\'t leak: this .lin is left over from an earlier compile ('+esc(L.src)+'). The trail may no longer mean anything.</div>';
  if(L.old)h+='<div class="warn">The .lin is older than the .map beside it: the map was saved after the compile that leaked, so this hole may already be sealed. Compile again to know.</div>';
  // -- what the compiler found
  const stale=D.kind==='bsp'&&GV&&GV.pvs;
  h+='<h4>Found</h4><div class="note">'+(stale?'When this .lin was written, the map wasn\'t sealed: ':'The map isn\'t sealed: ')+'the open space inside it joins the void outside. The compiler (q3map) fills the open space from each entity in turn; when that fill gets out of the map it stops, writes this trail and leaves out the vis'+(GV&&!GV.pvs?' (this .bsp has none)':'')+', so the whole map is drawn from everywhere and the outside faces aren\'t removed.</div>';
  h+=kvTable([
    ['starts','in the void outside the map, '+pr(p[0])+go(0)],
    ['gets in',F&&F.p&&!F.entOut?'<span style="color:#40e0ff">'+pr(F.p)+'</span> <button class="sm" data-go="'+F.p.join(' ')+'" data-from="'+(Math.hypot(F.p[0]-F.from[0],F.p[1]-F.from[1],F.p[2]-F.from[2])>8?F.from:p[Math.max(0,F.i-1)]).join(' ')+'" title="Fly to it, looking from the trail\'s side">Go</button>'+copyBtn(fvec(F.p))+(Math.hypot(F.p[0]-F.from[0],F.p[1]-F.from[1],F.p[2]-F.from[2])>8?' (seen from the trail at '+pr(F.from)+', near point '+(F.i+1)+')':' (near point '+(F.i+1)+')'):'<span class="co">not found along the trail</span>'],
    ['reaches',ename+' '+pr(p[p.length-1])+go(p.length-1)]]);
  // -- where it gets in, measured
  if(F&&F.entOut){
    h+='<h4>Recommended fix</h4><div class="note warn">The entity itself is out in the void: from its origin nothing that seals the map is in the way. Move '+(ei>0?esc(entName(ei)):'it')+' inside the map (or delete it), then compile again.</div>';
  }else if(F&&F.p){
    // (where the void comes through terrain or the like, the space round it isn't the gap)
    const gaps=F.cover?[]:F.ax.map((a,k)=>[a,k]).filter(([a])=>isFinite(a.w)&&a.w<1024).sort((x,y)=>x[0].w-y[0].w);
    const nm=['x','y','z'],gw=gaps.length?gaps[0][0].w:Infinity;
    const prims=[...new Set(gaps.length?gaps[0][0].pr:[])];
    const rows=[];
    if(gaps.length)rows.push(['the gap',gaps.map(([a,k])=>'<b>'+fnum(Math.round(a.w*100)/100)+'</b> unit'+(a.w===1?'':'s')+' along '+nm[k]+' ('+fnum(Math.round(a.lo*100)/100)+' to '+fnum(Math.round(a.hi*100)/100)+')').join(', ')]);
    rows.push(['the void','in a straight line '+esc(leakDirName(F.dir))+' from there'+(F.out.length>1?' ('+F.out.length+' of 26 ways)':'')]);
    if(prims.length)rows.push(['either side',prims.map(pi=>'brush '+SC.prims[pi].bn+(SC.prims[pi].ent?'/e'+SC.prims[pi].ent:'')).join(', ')+' <button class="sm" data-selprims="'+prims.join(',')+'" title="Select the brushes on either side of the gap and fly to them">Select them</button>']);
    rows.push(['in sight','the void is in a straight line from the trail along its first '+fnum(Math.round(F.run))+' units (points 1 to '+(F.i+1)+')']);
    if(F.cover)rows.push(['through',esc(F.cover.kind)+(F.cover.pi!=null?' ('+(SC.prims[F.cover.pi].kind===2?'terrain block ':SC.prims[F.cover.pi].kind===1?'patch ':'brush ')+SC.prims[F.cover.pi].bn+(SC.prims[F.cover.pi].ent?'/e'+SC.prims[F.cover.pi].ent:'')+') <button class="sm" data-selprims="'+F.cover.pi+'" title="Select it and fly to it">Select it</button>':'')+(F.cover.ent>0?' of '+linkEnt(F.cover.ent):'')+': the game collides with it, but the compiler doesn\'t take it as a seal, so the void comes in behind it']);
    h+='<h4>Where it gets in</h4><div class="note">Found from the last place along the trail from which the void is still in a straight line, before sealing brushes shut it in, looking that way: '+(F.cover?'the first thing in the way is something that doesn\'t seal':'where the way out passes closest to the sealing brushes')+' (the light blue circle).</div>'+kvTable(rows);
    h+='<h4>Recommended fix</h4><ul class="note" style="margin:4px 0 4px 16px;padding:0">';
    // the gap's sides off the grid: fractions of a unit
    const fr=gaps.length&&[gaps[0][0].lo,gaps[0][0].hi].some(v=>v!=null&&Math.abs(v-Math.round(v))>0.01);
    if(F.cover){const k=F.cover.kind;
      h+='<li>The void comes in behind '+(k==='terrain'?'the terrain':k==='patch'?'a patch':'a '+esc(k))+', which the compiler doesn\'t take as a seal'+(k==='terrain'?' (it is only a surface)':'')+'. Put structural caulk brushes '+(F.dir[2]<-0.5?'under':'behind')+' it, the whole way along, so the open space is shut in by brushes alone'+(k==='detail brush'?', or make that brush structural':'')+'.</li>';}
    else if(gw<2||fr)h+='<li>A hairline crack: two brushes that should meet don\'t quite'+(fr?', their faces at fractions of a unit (off the grid)':'')+'. Select them (Select them above), snap them to the grid in MOHRadiant (Ctrl+G) or pull one face so they overlap.</li>';
    else if(gw<16)h+='<li>A small gap between brushes: stretch one of them so they meet or overlap.</li>';
    else h+='<li>An opening to the void: a wall, floor or sky is missing there'+(gaps.length?' ('+gaps.map(([a,k])=>fnum(Math.round(a.w))+' across '+nm[k]).join(', ')+')':'')+'. Close it with a structural brush (caulk where it won\'t be seen, sky overhead). It only has to be solid, structural (not detail) and not see-through.</li>';
    h+='<li>Then compile again: the .lin is written again only if the map still leaks, maybe somewhere else.</li></ul>';
  }
  // -- reading it
  h+='<h4>Reading the trail</h4><div class="note">It isn\'t a way anyone walks. The compiler cuts the open space into convex cells (BSP leafs: along brush faces and on 1024-unit lines) and the trail is the fewest cells from outside to the entity, through the middle of each opening between two cells: hence the long straight runs along the 1024-unit lines and the turns where cells meet. The entity at its end is just the first one, by number, whose open space the void reaches; any entity in there would do, and it isn\'t wrong unless it is itself outside. Click a point or a circle in the view to find it here.</div>';
  h+='<h4>Points<span class="sp"></span>'+copyBtn(p.map(fvec).join('\n'),'Copy all')+'</h4>';
  h+='<table>'+p.slice(0,200).map((q,i)=>'<tr id="leakp'+i+'"'+(i===LEAKSEL?' style="background:rgba(64,224,255,.15)"':'')+'><td class="k">'+(i+1)+(i===0?' start':i===p.length-1?' entity':F&&F.i===i&&!F.entOut?' gap':'')+'</td><td>'+esc(fvec(q))+go(i)+'</td></tr>').join('')+'</table>';
  if(p.length>200)h+='<div class="note">… and '+(p.length-200)+' more (Copy all has them)</div>';
  card('Leak trail',h);
  if(LEAKSEL>=0){const r=$('leakp'+LEAKSEL);if(r)r.scrollIntoView({block:'center'});}
}
// a click on the trail in the 3D view: its nearest point, circle or the gap, within 10 pixels
function leakClick(x,y){
  if(!view.leak||!leakHas())return false;
  const P=D.leak.p,F=leakFix();let best=10*10,bi=-2;
  const cand=P.map((q,i)=>[q,i]);if(F&&F.p&&!F.entOut)cand.push([F.p,F.i]);
  for(const[q,i]of cand){const s=project(q);if(!s)continue;const d=(s[0]-x)**2+(s[1]-y)**2;if(d<best){best=d;bi=i;}}
  if(bi<-1)return false;
  LEAKSEL=bi;
  const ei=leakEnt();if(bi===P.length-1&&ei>0){SEL.clear();SEL.add('e'+ei);lastHit=null;selectionChanged();}
  leakCard();requestDraw();
  flash('Leak trail point '+(bi+1)+': '+fvec(P[bi]));
  return true;
}
// a look at a point, close enough to see what is around it: from the side of point
// "from" when given (no further than 80% of the way there), else from where the camera is
function flyLook(c,r,from){
  let dist=Math.max(64,r||160),dir=null;
  if(from){dir=vnorm(vsub(c,from));if(dir)dist=Math.min(dist,Math.max(8,0.8*Math.hypot(c[0]-from[0],c[1]-from[1],c[2]-from[2])));}
  dir=dir||vnorm(vsub(c,cam.pos))||camAxes().f;
  const yaw=Math.atan2(dir[1],dir[0])*180/Math.PI, pitch=-Math.asin(Math.max(-1,Math.min(1,dir[2])))*180/Math.PI;
  flyTo([c[0]-dir[0]*dist,c[1]-dir[1]*dist,c[2]-dir[2]*dist],yaw,pitch);requestDraw();
}

// ---- weather: rain and snow (Weather, Y; cg_rain_* in the game cvars) ---------------------
// As the client makes it (cgame/cg_nature.cpp CG_Rain, cg_beam.cpp): every client frame
// (com_maxfps a second), each func_rain the client has (in the snapshot: its box touches a
// cluster the player's PVS sees) starts sqrt(width x depth) x density / 200 drops in its box
// cut to rain_min_dist round the viewer (a square), the ones outside that circle skipped.
// A drop is a beam from its start to a point at the bottom of the box slant (and the wind,
// vss_wind_x / _y) across, at speed + a random part of speed_vary: it starts at the top of
// the box in Allied Assault 1.11, anywhere in its height in 2.0 / OpenMoHAA (with a 10 s
// most), and is drawn as a streak "length" long and twice "width" wide, facing the camera
// sideways (CG_BuildRendererBeam_Fast). Each beam keeps the shader, length and width it was
// started with (CG_CreateBeam stores them), so changing those cvars, or cg_weather, only
// changes the drops started after it. The snow shaders turn it into a little square
// facing the camera (deformVertexes autoSprite). Drops go through roofs: nothing stops one
// before the bottom of its box. All beams share MAX_BEAMS (4096): with none free a drop
// isn't started, which is what makes the gaps and clumps of slow snow from high boxes.
// The random numbers are the game's: rand() once a frame, then the client's own
// 214013 x + 2531011 step on the 15-bit value. The shader: one per box per frame,
// shader + a random 0 .. numshaders - 1 (cg_main.c).
const VS_WX=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV;
uniform mat4 uVP; out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
void main(){vUV=aUV;vPos=aPos;vCol=vec4(1.0);vPick=0.0;gl_Position=uVP*vec4(aPos,1.0);}`;
const WX_MAX=4096;                         // MAX_BEAMS (cg_commands.h)
const WX={P:null,vao:null,bP:null,bT:null,
  sx:new Float32Array(WX_MAX),sy:new Float32Array(WX_MAX),sz:new Float32Array(WX_MAX),
  ex:new Float32Array(WX_MAX),ey:new Float32Array(WX_MAX),ez:new Float32Array(WX_MAX),
  end:new Float64Array(WX_MAX),life:new Float64Array(WX_MAX),sh:new Int16Array(WX_MAX),on:new Uint8Array(WX_MAX),
  len:new Float32Array(WX_MAX),wid:new Float32Array(WX_MAX),shTab:[],shIds:new Map(),
  free:[],n:0,t:0,wall:0,seed:1,rainEnts:[],world:null,mapDef:{},
  stat:{at:0,made:0,missed:0,frames:0,last:null},names:[],nameKey:''};
// The rain cvars and the level settings they stand for (Level::SetRain*, the CS_RAIN_*
// configstrings the client reads into cg.rain).
const WX_KEYS=['density','speed','speed_vary','slant','length','min_dist','width','shader','numshaders'];
// weather.scr's presets (cg_weather), its "snow_original" and "rain_original" being the
// game's own snow (m6l1a) and the client's defaults
const WX_PRESETS={
  snow:[1,50,25,500,3,1800,2,'textures/snow10',0],snow_fast:[1,150,50,900,3,1800,2,'textures/snow10',0],
  blizzard:[3,350,150,1500,4,1800,3,'textures/snow10',0],hail:[0.25,1000,250,75,4,2048,3,'textures/snow10',0],
  snow_original:[0.2,32,16,250,2,1800,1,'textures/snow10',0],rain:[1,2048,512,75,50,1024,0.5,'textures/rain',0],
  drizzle:[0.1,2048,512,50,50,2048,0.5,'textures/rain',0],monsoon:[3,2048,512,250,50,1024,0.5,'textures/rain',0],
  rain_original:[1,2048,512,50,90,512,0.4,'textures/rain',0],off:[0,0,0,0,0,0,0,'textures/rain',0]};
// preset order: density, speed, speed_vary, slant, length, min_dist, width, shader, numshaders
const WX_PRESET_KEYS=['density','speed','speed_vary','slant','length','min_dist','width','shader','numshaders'];
// The map's own settings, as its script makes them, become the cvars' defaults; a map that
// runs global/weather.scr changes its density as it plays (a storm cycle): the viewer starts
// at that script's middle setting (width .4, min_dist 512, density 3, slant 50).
function wxInit(){
  const W=D.weather||{},S=W.set||{},def={};
  if(W.wscr){def.width=0.4;def.min_dist=512;def.density=3;def.slant=50;}
  for(const k of WX_KEYS){const s=S[k];if(s&&s[0]!=null&&s[0]!=='')def[k]=(k==='shader')?String(s[0]):parseFloat(s[0]);}
  for(const k in def){const n='cg_rain_'+k;if(k==='shader'||isFinite(def[k])){
    const v=k==='shader'?def[k]:(k==='numshaders'||k==='slant'||k==='speed_vary'?Math.trunc(def[k]):def[k]);
    CVAR_DEFAULTS[n]=v;CVARS[n]=v;WX.mapDef[n]=v;}}
  // a map whose own settings make nothing fall (no density from its script, as on every map
  // without func_rain): the viewer starts at the "rain" preset instead, so Weather shows
  // something (from the sky); cg_weather map still gives the map's own
  if(!(+CVARS.cg_rain_density>0)){
    WX_PRESET_KEYS.forEach((k,i)=>{const n='cg_rain_'+k,v=WX_PRESETS.rain[i];CVAR_DEFAULTS[n]=v;CVARS[n]=v;});
    CVAR_DEFAULTS.cg_weather='rain';CVARS.cg_weather='rain';WX.noMapRain=true;}
  // weather.scr's tree sway at its middle storm: (raindensity 3 + 1.5) / 2.5
  if(W.wscr){CVAR_DEFAULTS.r_static_shadermultiplier1=1.8;CVARS.r_static_shadermultiplier1=1.8;}
  WX.rainEnts=[];for(let ei=1;ei<MAP.ents.length;ei++)if(MAP.ents[ei].cls==='func_rain')WX.rainEnts.push(ei);
  for(let i=WX_MAX-1;i>=0;i--)WX.free.push(i);
  WX.seed=(Date.now()&0x7fffffff)|1;
}
function wxGL(){
  WX.P=compile(VS_WX,FS_MAIN);
  WX.bP=gl.createBuffer();WX.bT=gl.createBuffer();
  WX.vao=gl.createVertexArray();gl.bindVertexArray(WX.vao);attr(0,WX.bP,3);attr(1,WX.bT,2);gl.bindVertexArray(null);
}
// cg_weather: one of weather.scr's presets, or "map" for the map's own settings
function wxPreset(name){
  name=String(name||'').toLowerCase();
  if(name==='map'){for(const k of WX_KEYS){const n='cg_rain_'+k;CVARS[n]=(n in WX.mapDef)?WX.mapDef[n]:WX_BASE[n];}return true;}
  const p=WX_PRESETS[name==='0'?'off':name];if(!p)return false;
  WX_PRESET_KEYS.forEach((k,i)=>{CVARS['cg_rain_'+k]=p[i];});return true;
}
// the client's starting values (ClientGameCommandManager::InitializeRainCvars)
const WX_BASE={cg_rain_density:0,cg_rain_speed:2048,cg_rain_speed_vary:512,cg_rain_slant:50,cg_rain_length:90,
  cg_rain_min_dist:512,cg_rain_width:1,cg_rain_shader:'textures/rain',cg_rain_numshaders:0};
// the shaders (CS_RAIN_SHADER / CS_RAIN_NUMSHADERS in cg_main.c): numshaders of them, the
// shader's name with 0, 1, 2 ... after it (a digit it ends with dropped first, as
// OpenMoHAA does), else the shader itself
function wxNames(){
  const key=CVARS.cg_rain_shader+'|'+CVARS.cg_rain_numshaders;if(WX.nameKey===key)return WX.names;
  let s=String(CVARS.cg_rain_shader||'').trim().toLowerCase();const n=Math.max(0,Math.min(32,Math.trunc(CVARS.cg_rain_numshaders)||0));
  const out=[];
  if(n){if(/\d$/.test(s))s=s.slice(0,-1);for(let i=0;i<n;i++)out.push(s+i);}else if(s)out.push(s);
  WX.names=out;WX.nameKey=key;return out;
}
// a shader name's number in WX.shTab (a beam keeps the number of the shader it started with)
function wxShId(name){let id=WX.shIds.get(name);if(id==null){id=WX.shTab.length;WX.shTab.push(name);WX.shIds.set(name,id);}return id;}
function wxTex(name){const t=D.weather&&D.weather.tex&&D.weather.tex[name];return t||null;}
// the rain boxes the client has: each func_rain in the snapshot (its box in a cluster the
// camera's PVS sees), and with cg_rain_wholemap the whole map's
function wxVolumes(){
  const out=[];
  if(GV)gvCamera();
  // no func_rain shown (none in the map, or Hide hid them all): from the sky instead
  if(wxSkyMode()){if(!WX.world)WX.world=worldBounds();out.push([WX.world.mins,WX.world.maxs,-2]);}
  else for(const ei of WX.rainEnts){if(hidEnt.has(ei))continue;const B=gameBox(ei);if(!B||(GV&&!gvSent(GV,ei)))continue;
    const mn=[B.o[0]+B.mins[0],B.o[1]+B.mins[1],B.o[2]+B.mins[2]],mx=[B.o[0]+B.maxs[0],B.o[1]+B.maxs[1],B.o[2]+B.maxs[2]];
    if(mx[0]>mn[0]&&mx[1]>mn[1])out.push([mn,mx,ei]);}
  if(CVARS.cg_rain_wholemap){if(!WX.world)WX.world=worldBounds();out.push([WX.world.mins,WX.world.maxs,-1]);}
  return out;
}
// ---- weather from the sky ------------------------------------------------------------------
// The viewer's own addition, for maps without func_rain (or with every one hidden with
// Hide): drops start under the highest sky brush whose footprint covers their spot and fall
// to the first solid thing under it (a roof, the ground, a lower sky brush), so a spot with
// no sky brush above it (a tunnel, an indoor map such as mohdm7's covered streets) gets
// none, and rain never falls through a roof. The game has nothing like it: in game, rain
// falls only in func_rain boxes, through anything inside them.
function wxSkyBrushes(){
  if(WX.sky)return WX.sky;
  if(!SC||!TEX)return [];
  const L=[];
  for(const p of SC.prims){if(p.kind!==0||!WORLDLIKE[MAP.ents[p.ent].cls]||!isFinite(p.mins[0]))continue;
    let sky=false;for(let f=p.f0;f<p.f1;f++)if(TEX[SC.faceTex[f]].f&TF_SKY){sky=true;break;}
    if(sky)L.push([p.mins[0],p.mins[1],p.mins[2],p.maxs[0],p.maxs[1]]);}
  return WX.sky=L;
}
function wxSkyMode(){return !WX.rainEnts.some(ei=>!hidEnt.has(ei))&&wxSkyBrushes().length>0;}
// a 16-unit column's sky (the bottom of the highest sky brush over it) and what the drops
// land on under it, worked out once; null where no sky brush covers it or nothing is under
const WX_COL=16;
function wxCol(x,y){
  const cx=Math.floor(x/WX_COL),cy=Math.floor(y/WX_COL),k=cx+','+cy;
  if(!WX.cols)WX.cols=new Map();
  if(WX.cols.has(k))return WX.cols.get(k);
  const px=(cx+0.5)*WX_COL,py=(cy+0.5)*WX_COL;let top=-Infinity;
  for(const b of wxSkyBrushes())if(px>=b[0]&&px<=b[3]&&py>=b[1]&&py<=b[4]&&b[2]>top)top=b[2];
  let c=null;
  if(top>-Infinity){const s=[px,py,top-1],lo=WX.world?WX.world.mins[2]-1:top-65536,t=expTrace(s,[px,py,lo],[0,0,0],[0,0,0]);
    if(!t.startsolid&&t.f<1){const bot=s[2]+(lo-s[2])*t.f;if(top-bot>1)c=[top,bot];}}
  WX.cols.set(k,c);return c;
}
function wxRand(){WX.seed=(Math.imul(WX.seed,214013)+2531011)>>>0;return (WX.seed>>>16)&0x7fff;}   // MSVC rand()
function wxStep(r){return ((Math.imul(214013,r)+2531011)>>16)&0x7fff;}                           // CG_Rain's own
// one CG_Rain for one box (sky: the viewer's sky weather, each drop in its own column)
function wxRain(mn,mx,sky){
  const md=+CVARS.cg_rain_min_dist||0,vo=cam.pos;
  const x0=Math.max(mn[0],vo[0]-md),y0=Math.max(mn[1],vo[1]-md),z0=mn[2];
  const x1=Math.min(mx[0],vo[0]+md),y1=Math.min(mx[1],vo[1]+md),z1=mx[2];
  if(x0>x1||y0>y1)return;
  const ex=x1-x0,ey=y1-y0,ez=z1-z0;
  let n=Math.trunc(Math.sqrt(ex*ey)*((+CVARS.cg_rain_density||0)/200));
  if(n>WX_MAX)n=WX_MAX;
  let r=wxRand();
  const names=wxNames(),si=names.length?wxShId(names[Math.trunc(CVARS.cg_rain_numshaders)>0?r%names.length:0]):-1,
    blen=+CVARS.cg_rain_length||0,bwid=+CVARS.cg_rain_width||0;
  const v2=CVARS.com_target_game>=1,slant=Math.trunc(CVARS.cg_rain_slant)||0,vary=Math.trunc(CVARS.cg_rain_speed_vary)||0,
    speed=+CVARS.cg_rain_speed||0,wx=+CVARS.vss_wind_x||0,wy=+CVARS.vss_wind_y||0,md2=md*md;
  const mx0=Math.trunc(ex+1),my0=Math.trunc(ey+1),mz0=Math.trunc(ez+1);
  for(let i=0;i<n;i++){
    const sx=(r%mx0)+x0;r=wxStep(r);
    const sy=(r%my0)+y0;r=wxStep(r);
    // 2.0 / OpenMoHAA: anywhere in the box's height; 1.11: at its top
    let sz=v2?(r%mz0)+z0:z1,zb=z0;
    const dx=vo[0]-sx,dy=vo[1]-sy;
    if(dx*dx+dy*dy>md2)continue;
    if(sky){const c=wxCol(sx,sy);if(!c)continue;zb=c[1];sz=v2?(r%Math.trunc(c[0]-c[1]+1))+c[1]:c[0];}
    r=wxStep(r);
    const exx=(slant>0?r%slant:0)+sx+wx;r=wxStep(r);
    const eyy=(slant>0?r%slant:0)+sy+wy;
    const sp=(vary>0?r%vary:0)+speed;
    let life=sp>0?Math.trunc((sz-zb)/sp*1000):1e9;
    if(v2&&life>10000)life=10000;
    if(!WX.free.length){WX.stat.missed++;continue;}
    const b=WX.free.pop();
    WX.sx[b]=sx;WX.sy[b]=sy;WX.sz[b]=sz;WX.ex[b]=exx;WX.ey[b]=eyy;WX.ez[b]=zb;
    WX.end[b]=WX.t+life;WX.life[b]=life;WX.sh[b]=si;WX.len[b]=blen;WX.wid[b]=bwid;WX.on[b]=1;WX.n++;WX.stat.made++;}
}
// one client frame: the boxes' new drops (CG_AddPacketEntities), then the beams whose
// time is up freed (CG_AddBeams)
function wxFrame(vols){
  if(CVARS.cg_rain)for(const v of vols)wxRain(v[0],v[1],v[2]===-2);
  const t=WX.t;
  for(let b=0;b<WX_MAX;b++)if(WX.on[b]&&WX.end[b]<t){WX.on[b]=0;WX.n--;WX.free.push(b);}
  WX.stat.frames++;
}
// Run the client frames due since the last call (each 1000 / com_maxfps ms, as many as
// the game would have run), at most a fifth of a second's worth at once.
function wxAdvance(now){
  if(!WX.wall){WX.wall=now;return;}
  const ms=Math.max(1,Math.floor(1000/Math.max(1,+CVARS.com_maxfps||85)));
  let due=Math.floor((now-WX.wall)/ms);
  if(due<=0)return;
  WX.wall+=due*ms;
  if(due>Math.ceil(200/ms)){WX.t+=(due-Math.ceil(200/ms))*ms;due=Math.ceil(200/ms);}
  const vols=wxVolumes();WX.vols=vols.length;
  for(let i=0;i<due;i++){WX.t+=ms;wxFrame(vols);}
  // the last second, for the list's foot
  if(now-WX.stat.at>=1000){WX.stat.last={made:WX.stat.made,missed:WX.stat.missed,frames:WX.stat.frames,secs:(now-WX.stat.at)/1000};
    WX.stat.made=WX.stat.missed=WX.stat.frames=0;WX.stat.at=now;}
}
// keep running while drops are falling or can start
function wxActive(){return WX.n>0||(!!CVARS.cg_rain&&(+CVARS.cg_rain_density>0)&&(WX.rainEnts.length>0||!!CVARS.cg_rain_wholemap||wxSkyBrushes().length>0));}
function drawWeather(vp){
  if(!WX.n||!WX.P)return;
  const t=WX.t,a=camAxes(),L=[-a.r[0],-a.r[1],-a.r[2]],U=a.u;
  const groups=new Map();
  for(let b=0;b<WX_MAX;b++){if(!WX.on[b]||!(WX.life[b]>0))continue;let g=groups.get(WX.sh[b]);if(!g){g=[];groups.set(WX.sh[b],g);}g.push(b);}
  const P=new Float32Array(WX.n*18),T=new Float32Array(WX.n*12),ops=[];let q=0;
  const put=(v,s,t2)=>{P[q*3]=v[0];P[q*3+1]=v[1];P[q*3+2]=v[2];T[q*2]=s;T[q*2+1]=t2;q++;};
  for(const[si,list]of groups){
    const name=si>=0?WX.shTab[si]:null,tx=name?wxTex(name):null,ti=tx?tx[0]:-1,te=ti>=0?TEX[ti]:null,sprite=!!(te&&(te.f&TF_SPRITE));
    const first=q;
    for(const b of list){
      const fade=(WX.end[b]-t)/WX.life[b],len=WX.len[b],sc=WX.wid[b];
      const dx=WX.ex[b]-WX.sx[b],dy=WX.ey[b]-WX.sy[b],dz=WX.ez[b]-WX.sz[b],dl=Math.hypot(dx,dy,dz)||1;
      const hx=WX.sx[b]+(1-fade)*dx,hy=WX.sy[b]+(1-fade)*dy,hz=WX.sz[b]+(1-fade)*dz;
      const tx2=hx-dx/dl*len,ty2=hy-dy/dl*len,tz2=hz-dz/dl*len;
      const p0=[hx+L[0]*sc,hy+L[1]*sc,hz+L[2]*sc],p1=[tx2+L[0]*sc,ty2+L[1]*sc,tz2+L[2]*sc],
        p2=[tx2-L[0]*sc,ty2-L[1]*sc,tz2-L[2]*sc],p3=[hx-L[0]*sc,hy-L[1]*sc,hz-L[2]*sc];
      if(sprite){
        // deformVertexes autoSprite (tr_shade_calc.c AutospriteDeform): a square facing
        // the camera on the middle of the quad, its half-size 0.707 x a corner's distance
        const m=[(hx+tx2)/2,(hy+ty2)/2,(hz+tz2)/2],rad=Math.hypot(p0[0]-m[0],p0[1]-m[1],p0[2]-m[2])*0.707;
        const c=(sl,su)=>[m[0]+L[0]*rad*sl+U[0]*rad*su,m[1]+L[1]*rad*sl+U[1]*rad*su,m[2]+L[2]*rad*sl+U[2]*rad*su];
        const A=c(1,1),B2=c(-1,1),C=c(-1,-1),Dd=c(1,-1);
        put(A,0,0);put(B2,1,0);put(C,1,1);put(A,0,0);put(C,1,1);put(Dd,0,1);
      }else{put(p0,1,1);put(p1,0,1);put(p2,0,0);put(p0,1,1);put(p2,0,0);put(p3,1,0);}
    }
    ops.push([ti,first,q-first,tx?tx[1]:[1,1,1]]);
  }
  if(!q)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,WX.bP);gl.bufferData(gl.ARRAY_BUFFER,P.subarray(0,q*3),gl.STREAM_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,WX.bT);gl.bufferData(gl.ARRAY_BUFFER,T.subarray(0,q*2),gl.STREAM_DRAW);
  // an added shader fades to black in the fog (Q3's FP_BLACK), not to the fog's colour
  const Pr=WX.P;setCommon(Pr,vp,0);gl.uniform1f(Pr.u.uShade,0);gl.uniform3f(Pr.u.uFogCol,0,0,0);
  gl.bindVertexArray(WX.vao);gl.depthMask(false);
  for(const[ti,first,count,rgb]of ops){
    if(ti>=0){bindMat(Pr,ti,0);const k=(MAT[ti]||{}).kind||0;blendFor(k===0?3:k);}
    else{gl.bindTexture(gl.TEXTURE_2D,whiteTex);gl.uniform1i(Pr.u.uUseTex,1);gl.uniform1i(Pr.u.uAF,0);blendFor(3);}
    gl.disable(gl.CULL_FACE);gl.uniform4f(Pr.u.uTint,rgb[0],rgb[1],rgb[2],1);
    gl.drawArrays(gl.TRIANGLES,first,count);}
  gl.bindVertexArray(null);
}
function wxSummary(){
  const s=WX.stat.last,v=WX.vols|0;
  let h='weather: '+WX.n+' of '+WX_MAX+' beams falling, '+(wxSkyMode()?'from the sky ('+(WX.rainEnts.length?'every func_rain hidden':'no func_rain in this map')+')':'from '+v+' rain box'+(v===1?'':'es')+' the client has');
  if(s)h+=' · last second: '+s.made+' started'+(s.missed?', <span class="warn">'+s.missed+' not started (no free beam: MAX_BEAMS)</span>':'')+
    ' in '+s.frames+' client frames';
  return h;
}
function toggleWeather(){
  setCvar('cg_rain',CVARS.cg_rain?0:1);syncButtons();
  if(!CVARS.cg_rain){flash('Weather off (cg_rain 0)');return;}
  if(!WX.rainEnts.length&&!CVARS.cg_rain_wholemap&&!wxSkyBrushes().length){flash('Weather on, but this map has no func_rain and no sky: the game makes none here. cg_rain_wholemap 1 (game cvars, `) lets it fall over the whole map');return;}
  if(!(+CVARS.cg_rain_density>0)){flash('Weather on, but its density is 0'+(WX.noMapRain&&CVARS.cg_weather==='map'?' (this map sets no rain of its own)':'')+': set cg_rain_density, or cg_weather snow / rain (game cvars, `)');return;}
  flash('Weather on: '+(wxNames()[0]||'no shader')+', density '+CVARS.cg_rain_density+(wxSkyMode()?' · from the sky ('+(WX.rainEnts.length?'every func_rain is hidden':'no func_rain in this map')+')':''));
}

// ---- moving leaves: deformVertexes on models ----------------------------------------------
// A model surface whose shader has deformVertexes wave or flap (the trees' leaves: flap t 24
// sin 0 3.5 0 0.2 1 0) is moved in the model shader (VS_MODEL) by the game's time. A static
// model has no entity, so the renderer scales its wave's base, amplitude, phase and frequency
// by r_static_shadermultiplier0 .. 3 (tr_shade_calc.c); a model with an entity keeps its
// shader's. global/weather.scr sets r_static_shadermultiplier1 each second to
// (raindensity + 1.5) / 2.5, so a map's trees sway harder as its storm grows.
const DVT={at:0};
function dvUniforms(){
  gl.uniform1f(PM.u.uTime,(performance.now()-T0)/1000);
  gl.uniform4f(PM.u.uMul,+CVARS.r_static_shadermultiplier0||0,+CVARS.r_static_shadermultiplier1||0,
    +CVARS.r_static_shadermultiplier2||0,+CVARS.r_static_shadermultiplier3||0);
  gl.uniform4f(PM.u.uDv,0,0,0,1);
}
// any moving surface on a model that is drawn
function dvActive(){
  for(const R of MODELS)if(R.dv&&R.n)return true;
  return false;
}

// ---- thunder (cg_thunder) -------------------------------------------------------------------
// global/weather.scr's lightning (thunder, flash, unflash), without its sound: every
// level.thundertime + randomint(level.thundertime x 1.5) seconds one of three flickers (flash
// 0.2 s / 0.1 s, then off 1 s / 0.1 s ...), then 1 + randomfloat(2) seconds. A flash is
// r_fastsky 1 (no sky: the screen is cleared to the fog colour where the map has a farplane,
// else to 0.5 0.5 1), the farplane colour 0.9 0.9 0.9, and the map's $weatherF entities (the
// windows lit by the lightning) shown; unflash puts back the sky and the colour and hides
// them. level.thundertime starts at 20 and follows the storm (20, 8, 6, 4): the viewer keeps
// the map script's, else 6 (the middle storm) on a map that runs weather.scr, else 20.
const THU_PATTERNS=[[1,0.2,0,1,1,0.1,0,0.1,1,0.1,0],[1,0.1,0,0.1,1,0.1,0,1,1,0.2,0],[1,0.1,0,0.1,1,0.2,0,0.5,1,0.1,0]];
const THU={flash:false,next:0,ev:[],ents:null,hid:false};
function thTime(){const S=(D.weather&&D.weather.set)||{},t=S.thundertime&&parseFloat(S.thundertime[0]);
  return isFinite(t)&&t>0?t:(D.weather&&D.weather.wscr?6:20);}
function thEnts(){if(!THU.ents){THU.ents=new Set();MAP.ents.forEach((e,i)=>{if(i>0&&e.kvl.targetname==='weatherF')THU.ents.add(i);});}return THU.ents;}
function thSet(flash){
  THU.flash=flash;
  // the $weatherF windows: hidden while thunder runs, shown in a flash
  const hide=!!CVARS.cg_thunder&&!flash;
  if(hide!==THU.hid){THU.hid=hide;if(thEnts().size)rebuildWorld();}
  requestDraw();
}
function thTick(now){
  if(!CVARS.cg_thunder){if(THU.flash||THU.hid||THU.next){THU.next=0;THU.ev=[];thSet(false);}return;}
  const tt=thTime();
  if(!THU.next){THU.next=now+(tt+Math.floor(Math.random()*Math.floor(tt*1.5)))*1000;thSet(false);return;}
  if(!THU.ev.length&&now>=THU.next){
    const P=THU_PATTERNS[Math.floor(Math.random()*3)];let t=now;
    for(let i=0;i<P.length;i+=2){THU.ev.push([t,!!P[i]]);t+=(P[i+1]||0)*1000;}
    t+=(1+Math.random()*2)*1000;
    THU.next=t+(tt+Math.floor(Math.random()*Math.floor(tt*1.5)))*1000;}
  while(THU.ev.length&&THU.ev[0][0]<=now){const e=THU.ev.shift();if(e[1]!==THU.flash)thSet(e[1]);}
}

// ---- the sun flare (Sun flare, J) -------------------------------------------------------
// The game draws its sun only as a lens flare (RB_DrawSun is compiled out), after the 3D
// view (R_DrawLensFlares, renderergl1/tr_sun_flare.cpp): flat on the screen, over
// everything and unfogged. D.sun is this map's: the flare's direction (worldspawn
// sunflaredirection, else sundirection), its pictures, and dot_min, fullscale and fullfade
// from its section of global/lensflaredefs.txt ("sun" unless sunflarename names another).
// Each frame (sun_flare_class::SunTry, then lens_flare::ScreenBlend):
//  - nothing while the view's forward and the sun's direction have a dot product of
//    dot_min or less (CheckRange: .55 for "sun", about 57 degrees off);
//  - while the sun is seen (sunSeen), each flare at the brightness
//    (dot - dot_min) / (1 - dot_min), and the screen brightened (the glare) by that to the
//    4th power times fullscale;
//  - once it isn't, the glare fades out over fullfade milliseconds from there, and so does
//    the flare while the view still looks toward the sun (it drops to the glare's
//    brightness at once). With no fullscreen shader there is no glare and no fade.
// A flare is a square of +-size screen units (1 = half the view's width and half its
// height, so it stretches with the window), centred on the sun's place on the screen or
// 2 x where of the way from there through the middle; its picture is added (blendFunc
// GL_SRC_ALPHA GL_ONE, alphaGen fromClient) at that brightness times its alphascale. The
// glare is white, added (textures/jack/whitefade).
const VS_FLARE=`#version 300 es
layout(location=0) in vec2 aPos; layout(location=1) in vec2 aUV; out vec2 vUV;
void main(){vUV=aUV;gl_Position=vec4(aPos,0.0,1.0);}`;
const FS_FLARE=`#version 300 es
precision mediump float; in vec2 vUV; uniform sampler2D uTex; uniform vec4 uCol; out vec4 o;
void main(){o=texture(uTex,vUV)*uCol;}`;
// last: when the sun was last seen (lasttime); blend: the glare is on (blend_active);
// bright: the glare's brightness then (lastbright); lit: the sun was seen in the frame
// drawn last; key / seen: the camera position the line was last traced from, and what it met
const SUNF={P:null,tex:[],last:-1e9,blend:false,bright:0,lit:false,key:null,seen:false,solid:null};
function sunHas(){return !!(D&&D.sun&&D.sun.fl);}
function sunNone(){return (D&&D.sun&&D.sun.none)||'This page was built without the sun flare: rebuild the map.';}
function sunNow(){return performance.now();}          // the game's clock (refdef.time, in ms)
function setSunFlare(on){on=!!on;if(sunFlare===on)return;sunFlare=on;SUNF.blend=false;SUNF.lit=false;}
function sunFlareGL(){
  if(!sunHas())return;
  SUNF.P=compile(VS_FLARE,FS_FLARE);
  B.flare=gl.createBuffer();B.vFlare=gl.createVertexArray();gl.bindVertexArray(B.vFlare);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.flare);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,16,0);
  gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,2,gl.FLOAT,false,16,8);
  gl.bindVertexArray(null);
  // each picture: $whiteimage (no blob) is white, the others load like the textures
  SUNF.tex=D.sun.tx.map(t=>t[0]==null?whiteTex:null);
  D.sun.tx.forEach((t,i)=>{if(t[0]!=null)blobTexture(t[0],t[1],x=>{SUNF.tex[i]=x;});});
}
// SunCheckRay's line: CM_BoxTrace from the eye to 16384 units toward the sun, a point
// through the world model for CONTENTS_SOLID. It meets the solid brushes of worldspawn
// and func_group (not brush entities, models or static props), solid patches and the
// terrain; the sun is seen when the first thing met is a sky face (SURF_SKY). A brush is
// met as CM_TraceThroughBrush meets it; a brush with CONTENTS_FENCE lets a point through.
// The compiler's bevels are left out (a point never meets one first). A patch here is its
// drawn triangles met from either side (the game's facets, from the front: the line rarely
// starts behind one), the terrain its drawn triangles.
function sunSolids(){
  if(SUNF.solid)return SUNF.solid;
  const br=[],tr=[];
  const solid=(cont,te)=>{let c=(cont|0)&~CONTENTS_DETAIL;
    if(!c)c=(te.cf|0)|((te.p||[]).some(x=>CLEARS_SOLID.has(x))?0:1);
    return (c&1)&&!(c&0x2000);};
  const sky=(flags,te)=>((flags|0)&4)||(te.f&TF_SKY)?1:0;
  for(const p of SC.prims){
    if(!WORLDLIKE[MAP.ents[p.ent].cls]||!isFinite(p.mins[0]))continue;
    const pr=MAP.ents[p.ent].prims[p.bn];if(!pr||!pr.d)continue;
    if(p.kind===0){
      const faces=pr.d.faces;if(!faces.length||!solid(faces[0].cont,texFor(faces[0].tex)))continue;
      const pl=[],sk=[];
      for(const f of faces){const q=planeOf(f);if(q){pl.push(q);sk.push(sky(f.flags,texFor(f.tex)));}}
      if(pl.length)br.push({mn:p.mins,mx:p.maxs,pl:pl,sky:sk});
    }else if(p.kind===1){
      const te=texFor(pr.d.tex);if(!solid(pr.d.cont,te))continue;
      tr.push({mn:p.mins,mx:p.maxs,f0:p.f0,f1:p.f1,sky:sky(pr.d.flags,te)});
    }else tr.push({mn:p.mins,mx:p.maxs,f0:p.f0,f1:p.f1,sky:0});
  }
  return SUNF.solid={br:br,tr:tr};
}
// Does the line from e toward the sun (d) first meet a sky face?
function sunTrace(e,d){
  const L=16384, t=[e[0]+d[0]*L,e[1]+d[1]*L,e[2]+d[2]*L], EPS=0.125;   // SURFACE_CLIP_EPSILON
  const S=sunSolids();
  let best=1,sky=0;
  // is any of the line before what it has met so far inside the box (grown by a unit)?
  const reach=(mn,mx)=>{let a=0,b=best;
    for(let k=0;k<3;k++){
      if(Math.abs(d[k])<1e-9){if(e[k]<mn[k]-1||e[k]>mx[k]+1)return false;continue;}
      let t0=(mn[k]-1-e[k])/(d[k]*L),t1=(mx[k]+1-e[k])/(d[k]*L);if(t0>t1){const x=t0;t0=t1;t1=x;}
      if(t0>a)a=t0;if(t1<b)b=t1;if(a>b)return false;}
    return true;};
  for(const Bq of S.br){
    if(!reach(Bq.mn,Bq.mx))continue;
    let enter=-1,leave=1,lead=-1,startout=false,getout=false,miss=false;
    for(let k=0;k<Bq.pl.length;k++){const q=Bq.pl[k];
      const d1=e[0]*q[0]+e[1]*q[1]+e[2]*q[2]-q[3], d2=t[0]*q[0]+t[1]*q[1]+t[2]*q[2]-q[3];
      if(d1<=0&&d2<=0)continue;
      if(d2>0)getout=true;
      if(d1>0){startout=true;if(d2>=EPS||d2>=d1){miss=true;break;}}
      if(d1>d2){const f=Math.max(0,(d1-EPS)/(d1-d2));if(f>enter){enter=f;lead=k;}}
      else{const f=Math.min(1,(d1+EPS)/(d1-d2));if(f<leave)leave=f;}
    }
    if(miss)continue;
    if(!startout){if(!getout)return false;continue;}   // the eye inside it: the line goes on
    if(enter<=leave&&enter>-1&&enter<best){best=Math.max(0,enter);sky=Bq.sky[lead];}
  }
  const P=SC.pos,T=SC.tri,Dx=d[0]*L,Dy=d[1]*L,Dz=d[2]*L;
  for(const R of S.tr){
    if(!reach(R.mn,R.mx))continue;
    for(let f=R.f0;f<R.f1;f++)for(let i=SC.faceI0[f],ie=i+SC.faceIN[f];i+2<ie;i+=3){
      const a=T[i]*3,b=T[i+1]*3,c=T[i+2]*3;
      const ux=P[b]-P[a],uy=P[b+1]-P[a+1],uz=P[b+2]-P[a+2],vx=P[c]-P[a],vy=P[c+1]-P[a+1],vz=P[c+2]-P[a+2];
      const px=Dy*vz-Dz*vy,py=Dz*vx-Dx*vz,pz=Dx*vy-Dy*vx,det=ux*px+uy*py+uz*pz;
      if(Math.abs(det)<1e-9)continue;
      const sx=e[0]-P[a],sy=e[1]-P[a+1],sz=e[2]-P[a+2],u=(sx*px+sy*py+sz*pz)/det;
      if(u<0||u>1)continue;
      const qx=sy*uz-sz*uy,qy=sz*ux-sx*uz,qz=sx*uy-sy*ux,v=(Dx*qx+Dy*qy+Dz*qz)/det;
      if(v<0||u+v>1)continue;
      const f2=(vx*qx+vy*qy+vz*qz)/det;
      if(f2>0&&f2<best){best=f2;sky=R.sky;}
    }
  }
  return best<1&&!!sky;
}
// SunCheckRay traces only from a leaf that may see the sun: one outside the map or inside
// a wall (area -1), any leaf of a map without vis or whose leafs don't list the sun, else
// a leaf whose list of lights starts with the sun (R_LoadSphereLightVis: GV.sun). Any
// other leaf never sees it. A .map has none of that: the line alone decides.
function sunLeafOK(e){
  const G=GV;if(!G||!G.pvs||!G.sun)return true;
  const L=gvPointLeaf(G,e);
  return G.lf[L*14+1]===-1||!!G.sun[L];
}
// The line always runs the same way, so the answer changes only as the camera moves.
function sunSeen(){
  const e=cam.pos,key=e[0]+' '+e[1]+' '+e[2];
  if(SUNF.key!==key){SUNF.key=key;SUNF.seen=sunLeafOK(e)&&sunTrace(e,D.sun.d);}
  return SUNF.seen;
}
function sunBlendFactor(k){
  return [gl.ZERO,gl.ONE,gl.SRC_COLOR,gl.ONE_MINUS_SRC_COLOR,gl.DST_COLOR,gl.ONE_MINUS_DST_COLOR,gl.SRC_ALPHA,
    gl.ONE_MINUS_SRC_ALPHA,gl.DST_ALPHA,gl.ONE_MINUS_DST_ALPHA,gl.SRC_ALPHA_SATURATE][k|0]||gl.ONE;}
function drawSunFlare(vp){
  const S=D.sun;
  if(!sunFlare||!SUNF.P){SUNF.blend=false;SUNF.lit=false;return;}
  const now=sunNow(),a=camAxes(),d=S.d;
  const dot=a.f[0]*d[0]+a.f[1]*d[1]+a.f[2]*d[2], seen=dot>S.dm&&sunSeen();
  // The game draws every frame and the page only when something changes, so the frame
  // drawn before this one may be long ago: if the sun was in view in it, it stayed in
  // view until now (the game kept lasttime current all along), and a fade starts now.
  if(!seen&&SUNF.lit)SUNF.last=now;
  SUNF.lit=seen;
  let alpha=0;
  if(seen){alpha=(dot-S.dm)/(1-S.dm);SUNF.last=now;SUNF.blend=true;SUNF.bright=alpha*alpha*alpha*alpha*S.fs;}
  else if(dot>S.dm&&S.full&&SUNF.blend){const f=(S.ff-(now-SUNF.last))/S.ff*SUNF.bright;if(f>0.0001)alpha=f;}
  let glare=0;
  if(S.full&&SUNF.blend){const td=now-SUNF.last;
    if(td>S.ff)SUNF.blend=false;
    else{glare=(S.ff-td)/S.ff*SUNF.bright;if(glare<=0.0001){glare=0;SUNF.blend=false;}}}
  const V=[],runs=[];
  const quad=(x0,y0,x1,y1)=>V.push(x0,y0,0,0, x1,y0,1,0, x0,y1,0,1, x1,y0,1,0, x1,y1,1,1, x0,y1,0,1);
  if(alpha>0){
    // SunScreenCalc: where the point 128 units out toward the sun is on the screen
    const v=[cam.pos[0]+128*d[0],cam.pos[1]+128*d[1],cam.pos[2]+128*d[2]];
    const w=vp[3]*v[0]+vp[7]*v[1]+vp[11]*v[2]+vp[15];
    const sx=(vp[0]*v[0]+vp[4]*v[1]+vp[8]*v[2]+vp[12])/w, sy=(vp[1]*v[0]+vp[5]*v[1]+vp[9]*v[2]+vp[13])/w;
    for(const fl of S.fl){const tex=SUNF.tex[fl[3]];if(!tex)continue;
      const px=sx-2*sx*fl[1], py=sy-2*sy*fl[1], s=fl[0];
      quad(px-s,py+s,px+s,py-s);runs.push([tex,alpha*fl[2],S.tx[fl[3]]]);}
  }
  if(glare>0){quad(-1,1,1,-1);runs.push([whiteTex,glare,null]);}
  // a fade keeps the view redrawing until it ends
  if(S.full&&SUNF.blend&&!seen)requestDraw();
  if(!runs.length)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,B.flare);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(V),gl.STREAM_DRAW);
  gl.useProgram(SUNF.P);gl.bindVertexArray(B.vFlare);
  gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);
  gl.activeTexture(gl.TEXTURE0);gl.uniform1i(SUNF.P.u.uTex,0);
  runs.forEach((r,i)=>{const tx=r[2];
    gl.blendFunc(tx?sunBlendFactor(tx[2]):gl.SRC_ALPHA,tx?sunBlendFactor(tx[3]):gl.ONE);
    gl.bindTexture(gl.TEXTURE_2D,r[0]);gl.uniform4f(SUNF.P.u.uCol,1,1,1,Math.min(1,r[1]));
    gl.drawArrays(gl.TRIANGLES,i*6,6);});
  gl.bindVertexArray(null);gl.disable(gl.BLEND);gl.depthMask(true);gl.enable(gl.DEPTH_TEST);
}
// ---- turning the map's lights off (Display: Lights off; Selection: Turn off / Turn on) ----
// The game's light is baked: the lightmaps, the vertex light, the static props' light and
// the light grid hold the sum of every light the map compiler traced, and nothing in the
// game takes one out again. The page works out each light's share of that sum and keeps
// only the light above the map's ambient that the lights still on account for:
//   new = min(V, A) + max(V - A, 0) * (Won + Wsun) / (Won + Woff + Wsun)
// per colour channel, V the baked value and A the worldspawn's ambientlight (the compiler
// floors every texel at it: m6l3d's unlit texels are 5 5 5, m4l3's 7 10 15 for
// "7.75 10.3 15"). The weights W are each light's contribution as q3map computes it
// (LightContributionToSample, tools/ommap/light.c): intensity x 7500 / distance^2 x the
// angle to the surface, a spot light's cone, a linear light's straight falloff, nothing
// from behind the surface or under 1. It is seen through a shadow map of the drawn, opaque
// surfaces, as q3map traces against drawn surfaces (InitSurfacesForTesting: no
// translucent ones, no patches) and not brushes. Each light also gets a small weight
// without shadows within its reach: light the compiler spread further than the trace
// says goes with its lamp. On a map with sky, the sun weighs in too, through shadow maps
// toward the sun (suncolor x the angle) and toward the sky (sundiffuse).
// Only the shares are used: MOHAA's compiler compresses the brightest light near a lamp,
// in a way that isn't known, and a share doesn't depend on it. A lamp alone in a room
// takes the room down to its ambient light; with every light off, a map without sky is
// at its ambient light everywhere (min(V, A)).
// Nothing of this runs until a light is turned off. The first time, every light's
// weight is worked out (a few frames' work each, with progress in the bottom line), then
// each change only adds or takes out the lights it changes. Lightmap texels are worked
// out in the lightmap pages' own layout (LIT's polygons drawn at their lightmap
// coordinates); the texels just outside the polygons, which the lightmap's filtering
// reaches, take the factor of the texels beside them. Vertex light (triangle soups, a
// static prop's vertices) and each model's light-grid colour are points ("probes") done
// the same way: the props' vertices first, in the order of their baked light, so the
// result is read just as the baked light is (uStatic).
const LT={ok:null,why:'',lights:[],byEnt:new Map(),off:null,applied:null,nOff:0,active:false,
  prepped:false,totReady:false,busy:false,queue:[],want:null,entSlot:null,sun:[],
  fence:null,batch:4,step:'',crash:null,crashArm:0,settleT:0,
  sunOff:false,sunHas:false,sunWhy:'',what:'',
  // lam: the share each light also gets without shadows, within its reach; kap: how many
  // times that unshadowed light a light turned off may take away (FS_LTREL)
  lam:0.02,kap:2};
const LT_CUBE=512, LT_DIR=2048, LT_PW=4096;
// q3map's ValueForKey: the key as written, its last value (ParseEpair puts each new pair first)
function ltKey(e,k){let v=null;for(const p of e.kv)if(p[0]===k)v=p[1];return v;}
function ltNum(s,d){const v=parseFloat(s);return isFinite(v)?v:d;}
function ltVec(s){const m=String(s==null?'':s).trim().split(/\s+/).map(parseFloat);return(m.length>=3&&isFinite(m[0])&&isFinite(m[1])&&isFinite(m[2]))?m.slice(0,3):null;}
function ltForward(a){const p=a[0]*Math.PI/180,y=a[1]*Math.PI/180;return[Math.cos(p)*Math.cos(y),Math.cos(p)*Math.sin(y),-Math.sin(p)];}
// The lights as the compiler reads them (CreateEntityLights; MOHAA's spot lights and
// spot_angle as its sphere-light lump shows them): every entity whose class starts
// with "light". Spawnflags: 1 LINEAR, 2 NO_ENTITIES (the world only), 8 ENTITY_ONLY.
function ltLights(){
  const out=[];
  MAP.ents.forEach((e,ei)=>{
    if(!String(e.cls).startsWith('light'))return;
    const o=ltVec(ltKey(e,'origin'));if(!o)return;
    const sf=ltNum(ltKey(e,'spawnflags'),0)|0;
    let I=ltNum(ltKey(e,'light'),0);if(!I)I=ltNum(ltKey(e,'_light'),0);if(!I)I=300;
    let c=ltVec(ltKey(e,'_color')||ltKey(e,'color'))||[1,1,1];
    const m=Math.max(c[0],c[1],c[2]);c=m>0?c.map(x=>x/m):[0,0,0];          // ColorNormalize
    // a spot light: aimed at its target's origin, else along its "angles" (64 units on);
    // its cone's radius per unit of distance is (radius + 16) / that distance, or the
    // tangent of spot_angle
    let dir=null,dist=0;
    const tg=ltKey(e,'target');
    if(tg){const t=MAP.ents.find(x=>ltKey(x,'targetname')===tg),to=t?ltVec(ltKey(t,'origin')):null;
      if(to){const d=[to[0]-o[0],to[1]-o[1],to[2]-o[2]],l=Math.hypot(d[0],d[1],d[2]);dist=l;dir=l>0?d.map(x=>x/l):[0,0,-1];}}
    if(!dir&&ltKey(e,'angles')!=null){dir=ltForward(ltVec(ltKey(e,'angles'))||[0,0,0]);dist=64;}
    let rbd=0;
    if(dir){const sa=ltKey(e,'spot_angle');
      rbd=sa!=null?Math.tan(ltNum(sa,45)*Math.PI/180):((ltNum(ltKey(e,'radius'),0)||64)+16)/(dist||64);}
    const ph=I*7500, lin=!!(sf&1)&&!dir, fall=ltNum(ltKey(e,'falloff'),1)||1;
    // how far it reaches: where its light falls to 1
    const R=lin?Math.max(16,ph/8000/fall):Math.max(16,Math.sqrt(Math.max(0,ph)));
    out.push({ei:ei,o:o,ph:ph,c:c,R:R,lin:lin,fall:fall,dir:dir,rbd:rbd,world:!(sf&8),ents:!(sf&2)});
  });
  return out;
}
// Can lights be turned off here? A .map has no baked light; a .bsp needs lightmaps and the
// float render targets the weights are summed in.
function ltCheck(){
  if(LT.ok!==null)return LT.ok;
  LT.ok=false;
  if(D.kind!=='bsp'){LT.why='A .map has no baked light to turn off: the map compiler bakes the light into the .bsp (its lightmaps, vertex light and light grid). Open the .bsp to turn lights off.';return false;}
  if(!LIT){LT.why='This .bsp has no lightmaps, so there is no baked light to turn off.';return false;}
  LT.lights=ltLights();
  if(!LT.lights.length){LT.why='This map has no light entities: its light is all ambient and sun.';return false;}
  if(!gl.getExtension('EXT_color_buffer_float')){LT.why='This graphics driver can\'t draw into floating-point textures (EXT_color_buffer_float), which turning lights off needs.';return false;}
  LT.lights.forEach((l,i)=>{if(!LT.byEnt.has(l.ei))LT.byEnt.set(l.ei,i);});
  LT.off=new Uint8Array(LT.lights.length);LT.applied=new Uint8Array(LT.lights.length);
  LT.crash=ltCrumbRead();
  // Sun light: a sun or sky light that reaches the map (sky faces, a sun colour)
  LT.sunHas=ltSunDirs().some(x=>x[1][0]+x[1][1]+x[1][2]>0);
  LT.sunWhy=LT.sunHas?'':!ltHasSky()?'This map has no sky faces, so no sunlight reaches it.'
    :'This map has no sun: its worldspawn has no suncolor (or sunlight).';
  LT.ok=true;return true;
}
function ltIsLight(ei){return LT.ok&&LT.byEnt.has(ei);}
function ltLightOff(ei){const i=LT.byEnt.get(ei);return i!=null&&!!LT.off[i];}

// ---- the shaders ------------------------------------------------------------------------
// Distance maps: a cube around a light (six faces side by side in one texture, each drawn
// and read through the same matrix, so no face can come out turned) holding the distance
// to the nearest drawn surface; or one map toward the sun or the sky holding how far
// toward it the nearest surface is.
const VS_LTD=`#version 300 es
layout(location=0) in vec3 aPos; uniform mat4 uVP; out vec3 vP;
void main(){vP=aPos;gl_Position=uVP*vec4(aPos,1.0);}`;
const FS_LTD=`#version 300 es
precision highp float; in vec3 vP; uniform vec4 uL; out vec4 o;
void main(){o=vec4(uL.w>0.5?dot(vP,uL.xyz):length(vP-uL.xyz),0.0,0.0,1.0);}`;
// The weight shaders: a lightmap texel (drawn at its lightmap coordinates in the pages'
// atlas) or a probe (a point at its slot), and what one light or one sun / sky direction
// adds there. aN.w: 1 a one-sided surface, 0 two-sided (a patch: either side), -1 a model
// (no surface: lit from every side).
const VS_LTLM=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=8) in vec3 aLM; layout(location=13) in vec4 aN;
uniform vec3 uAt; out vec3 vP; out vec4 vN;
void main(){float pg=floor(aLM.z+0.5);vec2 c=vec2(mod(pg,uAt.x),floor(pg/uAt.x));
  vP=aPos;vN=aN;gl_Position=vec4(((c+aLM.xy)*uAt.yz)*2.0-1.0,0.0,1.0);}`;
const VS_LTPR=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=13) in vec4 aN; layout(location=14) in float aSlot;
uniform vec2 uPA; out vec3 vP; out vec4 vN;
void main(){float s=aSlot;vec2 t=vec2(mod(s,uPA.x)+0.5,floor(s/uPA.x)+0.5)/uPA;
  vP=aPos;vN=aN;gl_PointSize=1.0;gl_Position=vec4(t*2.0-1.0,0.0,1.0);}`;
const FS_LTW=`#version 300 es
precision highp float;
in vec3 vP; in vec4 vN;
uniform int uKind;          // 0 a light, 1 a sun / sky direction
uniform vec4 uL;            // light: origin, intensity x 7500; direction: toward it, unused
uniform vec4 uC;            // colour (light: normalized; direction: its weight), light's reach
uniform vec4 uS;            // spot direction, radius per unit of distance (0: not a spot)
uniform vec4 uF;            // linear light (1 / 0), its falloff, the share without shadows
uniform highp sampler2D uSh; uniform mat4 uFV[6]; uniform float uSz;
out vec4 o;
// The point is first moved off its surface by a cube texel and a half at its distance
// (n: the surface's normal, none for a model), so its own surface can't hide it, and the
// test allows two texels more: enough for a surface the light grazes, not enough to see
// through a wall. The maps are read texel by texel (uSz: a face's or the sun map's size).
float seenCube(vec3 p,vec3 n){
  float tx=2.0*length(p-uL.xyz)/uSz;
  p+=n*(1.5*tx);
  vec3 d=p-uL.xyz,a=abs(d);int f=(a.x>=a.y&&a.x>=a.z)?(d.x>0.0?0:1):((a.y>=a.z)?(d.y>0.0?2:3):(d.z>0.0?4:5));
  vec4 c=uFV[f]*vec4(p,1.0);vec2 uv=clamp(c.xy/max(c.w,1e-6)*0.5+0.5,vec2(0.0),vec2(1.0));
  ivec2 px=ivec2(min(uv*uSz,vec2(uSz-1.0)))+ivec2(f%3,f/3)*int(uSz);
  float s=texelFetch(uSh,px,0).r;
  return length(d)<=s+1.0+2.0*tx?1.0:0.0;}
float seenDir(vec3 p){
  vec4 c=uFV[0]*vec4(p,1.0);vec2 uv=c.xy*0.5+0.5;
  if(uv.x<0.0||uv.y<0.0||uv.x>1.0||uv.y>1.0)return 1.0;
  ivec2 px=ivec2(min(uv*uSz,vec2(uSz-1.0)));
  return dot(p,uL.xyz)>=texelFetch(uSh,px,0).r-2.0?1.0:0.0;}
void main(){
  vec3 n=vN.xyz, p=vP+(vN.w>-0.5?n:vec3(0.0));       // q3map samples 1 unit off the surface
  float w=0.0;
  if(uKind==1){
    float ang=vN.w>0.5?max(0.0,dot(n,uL.xyz)):(vN.w>-0.5?abs(dot(n,uL.xyz)):1.0);
    if(ang>0.0)w=ang*seenDir(p);
  }else{
    vec3 d=uL.xyz-p;float dl=length(d);
    if(dl<=uC.w){
      float dist=max(dl,16.0), ang=1.0;
      bool ok=true;
      if(vN.w>0.5){if(dot(uL.xyz-vP,n)<0.0)ok=false;ang=dot(n,d)/max(dl,1e-6);}
      else if(vN.w>-0.5)ang=abs(dot(n,d))/max(dl,1e-6);
      float add=0.0;
      if(ok){
        if(uS.w>0.0){float dbn=dot(p-uL.xyz,uS.xyz);
          if(dbn>=0.0){float rad=uS.w*dbn,sr=length(p-(uL.xyz+uS.xyz*dbn));
            if(sr<rad)add=uL.w/(dist*dist)*ang*(sr<=rad-32.0?1.0:(rad-sr)/32.0);}}
        else if(uF.x>0.5)add=ang*uL.w*(1.0/8000.0)-dist*uF.y;
        else add=uL.w/(dist*dist)*ang;
      }
      w=(add>1.0?add*seenCube(p,vN.w>0.5?n:(vN.w>-0.5?n*sign(dot(n,d)):vec3(0.0))):0.0)+uF.z*uL.w/(dist*dist);
    }
  }
  // a sixteenth, so the half floats summing them hold a texel next to many strong lights
  o=vec4(uC.rgb*w*0.0625,1.0);}`;
// Coverage: which atlas texels some lightmapped polygon covers
const FS_LTCOV=`#version 300 es
precision mediump float; out vec4 o; void main(){o=vec4(1.0);}`;
// The relit lightmap page / probes: the light above the ambient floor scaled by the share
// that stays on, taking out no more than the lights turned off could have given there.
// Each light adds its share without shadows (uF.z, its photons / distance squared) wherever
// it reaches, so OFF / that share bounds what they gave; uCap is twice that, in the
// page's units. A texel only a little of their light reaches keeps the rest of its light
// (sky light, light the compiler bent around a corner). With the sun off (uSunOn 0) its
// share goes too, and the light left is no more than the lights still on could give
// (TOT - OFF, bounded the same way): what nothing traced explains was the sky's.
const VS_LTQ=`#version 300 es
layout(location=0) in vec2 aQ; void main(){gl_Position=vec4(aQ,0.0,1.0);}`;
const FS_LTREL=`#version 300 es
precision highp float;
uniform highp sampler2DArray uBake; uniform highp sampler2D uTot; uniform highp sampler2D uOff;
uniform highp sampler2D uSun; uniform highp sampler2D uCov;
uniform int uLayer; uniform int uCols; uniform vec3 uA; uniform int uDark; uniform float uCap; uniform int uSunOn;
out vec4 o;
// the texels around one, the ring beside it first, then the one two texels out
const ivec2 NB[24]=ivec2[24](ivec2(-1,-1),ivec2(0,-1),ivec2(1,-1),ivec2(-1,0),ivec2(1,0),ivec2(-1,1),ivec2(0,1),ivec2(1,1),
  ivec2(-2,-2),ivec2(-1,-2),ivec2(0,-2),ivec2(1,-2),ivec2(2,-2),ivec2(-2,-1),ivec2(2,-1),ivec2(-2,0),
  ivec2(2,0),ivec2(-2,1),ivec2(2,1),ivec2(-2,2),ivec2(-1,2),ivec2(0,2),ivec2(1,2),ivec2(2,2));
vec3 fac(ivec2 a){vec3 t=texelFetch(uTot,a,0).rgb,f=texelFetch(uOff,a,0).rgb,s=texelFetch(uSun,a,0).rgb,d=t+s;
  float u=float(uSunOn);                      // nothing traced: kept with the sun, gone without
  vec3 on=max(t-f,vec3(0.0))+s*u;
  return clamp(vec3(d.r>1e-4?on.r/d.r:u,d.g>1e-4?on.g/d.g:u,d.b>1e-4?on.b/d.b:u),0.0,1.0);}
// what is left of X: no more taken out than the lights off could give (sun on), no more
// left than the lights still on could give (sun off)
vec3 left(vec3 X,vec3 F,vec3 t,vec3 f){
  if(uDark==1)return vec3(0.0);
  if(uSunOn==1)return max(X*F,X-uCap*max(f,vec3(0.0)));
  return min(X*F,uCap*max(t-f,vec3(0.0)));}
void main(){
  ivec2 t=ivec2(gl_FragCoord.xy), b=ivec2((uLayer%uCols)*128,(uLayer/uCols)*128);
  vec3 F=vec3(1.0),f=vec3(0.0),tt=vec3(0.0);
  if(texelFetch(uCov,b+t,0).r>0.5){F=fac(b+t);f=texelFetch(uOff,b+t,0).rgb;tt=texelFetch(uTot,b+t,0).rgb;}
  else{
    // a texel no polygon covers (the filtering reaches it) takes the factor of the covered
    // texels of the nearest ring that has any; loops of fixed length, nothing skipped
    vec3 s1=vec3(0.0),g1=vec3(0.0),h1=vec3(0.0),s2=vec3(0.0),g2=vec3(0.0),h2=vec3(0.0);float n1=0.0,n2=0.0;
    for(int i=0;i<8;i++){ivec2 q=t+NB[i],c=clamp(q,ivec2(0),ivec2(127));
      float w=(q==c?1.0:0.0)*step(0.5,texelFetch(uCov,b+c,0).r);
      s1+=fac(b+c)*w;g1+=texelFetch(uOff,b+c,0).rgb*w;h1+=texelFetch(uTot,b+c,0).rgb*w;n1+=w;}
    for(int i=8;i<24;i++){ivec2 q=t+NB[i],c=clamp(q,ivec2(0),ivec2(127));
      float w=(q==c?1.0:0.0)*step(0.5,texelFetch(uCov,b+c,0).r);
      s2+=fac(b+c)*w;g2+=texelFetch(uOff,b+c,0).rgb*w;h2+=texelFetch(uTot,b+c,0).rgb*w;n2+=w;}
    if(n1>0.0){F=s1/n1;f=g1/n1;tt=h1/n1;}else if(n2>0.0){F=s2/n2;f=g2/n2;tt=h2/n2;}
    else tt=vec3(1e4);                        // out of reach of every polygon: as it is
  }
  vec3 V=texelFetch(uBake,ivec3(t,uLayer),0).rgb,X=max(V-uA,vec3(0.0));
  o=vec4(min(V,uA)+left(X,F,tt,f),1.0);}`;
const FS_LTPREL=`#version 300 es
precision highp float;
uniform highp sampler2D uBake; uniform highp sampler2D uTot; uniform highp sampler2D uOff; uniform highp sampler2D uSun;
uniform vec3 uA; uniform int uDark; uniform float uCap; uniform int uSunOn;
out vec4 o;
void main(){ivec2 a=ivec2(gl_FragCoord.xy);
  vec3 t=texelFetch(uTot,a,0).rgb,f=texelFetch(uOff,a,0).rgb,s=texelFetch(uSun,a,0).rgb,d=t+s;
  float u=float(uSunOn);vec3 on=max(t-f,vec3(0.0))+s*u;
  vec3 F=clamp(vec3(d.r>1e-4?on.r/d.r:u,d.g>1e-4?on.g/d.g:u,d.b>1e-4?on.b/d.b:u),0.0,1.0);
  vec3 V=texelFetch(uBake,a,0).rgb,X=max(V-uA,vec3(0.0)),Y;
  if(uDark==1)Y=vec3(0.0);
  else if(uSunOn==1)Y=max(X*F,X-uCap*max(f,vec3(0.0)));
  else Y=min(X*F,uCap*max(t-f,vec3(0.0)));
  o=vec4(min(V,uA)+Y,1.0);}`;

// ---- matrices ----------------------------------------------------------------------------
function ltLook(e,f,u){   // view matrix from e looking along f, u roughly up (viewProj's layout)
  const r=vnorm(vcross(f,u)),uu=vcross(r,f);
  return [r[0],uu[0],-f[0],0, r[1],uu[1],-f[1],0, r[2],uu[2],-f[2],0, -vdot(r,e),-vdot(uu,e),vdot(f,e),1];}
function ltPersp(n,fz){return [1,0,0,0, 0,1,0,0, 0,0,-(fz+n)/(fz-n),-1, 0,0,-2*fz*n/(fz-n),0];}
function ltOrtho(h,n,fz){return [1/h,0,0,0, 0,1/h,0,0, 0,0,-2/(fz-n),0, 0,0,-(fz+n)/(fz-n),1];}
const LT_FACES=[[[1,0,0],[0,0,1]],[[-1,0,0],[0,0,1]],[[0,1,0],[0,0,1]],[[0,-1,0],[0,0,1]],[[0,0,1],[0,1,0]],[[0,0,-1],[0,1,0]]];

// ---- getting ready: the polygons' normals, the probes, the textures ----------------------
function ltTex(w,h,ifmt,fmt,type,filter){const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
  gl.texImage2D(gl.TEXTURE_2D,0,ifmt,w,h,0,fmt,type,null);
  for(const[p,v]of[[gl.TEXTURE_MIN_FILTER,filter],[gl.TEXTURE_MAG_FILTER,filter],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,p,v);
  return t;}
function ltFB(tex,depth){const f=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,f);
  gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,tex,0);
  if(depth)gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depth);
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);return f;}
function ltPrep(){
  if(LT.prepped)return;
  const nv=LIT.nv, P=LIT.pos, T=LIT.tri, LM=LIT.lm;
  // normals: a .bsp polygon's from its winding (its triangles run clockwise seen from the
  // front, so (c-a)x(b-a) is its normal), terrain's facing up, a patch's the .bsp's own
  // (from its control points; without them, from one of the two windings the page draws
  // it with, used from either side)
  const N=new Float32Array(nv*4), side=new Float32Array(nv);
  LT.units=[];
  LIT.units.forEach(u=>{
    if(!u.n)return;
    const k=u.k|0, te=TEX[u.ti]||{};
    let mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity],lmOn=false,vtx=false;
    for(let q=0;q<u.n;q+=3){
      if(k===1&&((q/3)%4)>=2)continue;
      const a=T[u.i0+q]*3,b=T[u.i0+q+1]*3,c=T[u.i0+q+2]*3;
      const e1=[P[c]-P[a],P[c+1]-P[a+1],P[c+2]-P[a+2]],e2=[P[b]-P[a],P[b+1]-P[a+1],P[b+2]-P[a+2]];
      let nn=vcross(e1,e2);if(k===2&&nn[2]<0)nn=[-nn[0],-nn[1],-nn[2]];
      for(const v of [a/3,b/3,c/3]){
        const pn=LIT.nrm&&k===1?[LIT.nrm[v*3],LIT.nrm[v*3+1],LIT.nrm[v*3+2]]:null, has=pn&&(pn[0]||pn[1]||pn[2]);
        if(has){N[v*4]=pn[0];N[v*4+1]=pn[1];N[v*4+2]=pn[2];side[v]=1;}
        else{N[v*4]+=nn[0];N[v*4+1]+=nn[1];N[v*4+2]+=nn[2];side[v]=k===1?0:1;}}
    }
    for(let q=0;q<u.n;q++){const v=T[u.i0+q];
      for(let j=0;j<3;j++){const x=P[v*3+j];if(x<mn[j])mn[j]=x;if(x>mx[j])mx[j]=x;}
      if(LM[v*3+2]>-0.5)lmOn=true;else if(LM[v*3+2]>-1.5)vtx=true;}
    // occluders: drawn, opaque surfaces; light passes see-through ones (CONTENTS_TRANSLUCENT),
    // alpha-tested ones (grates, fences: through their holes) and patches (q3map traces
    // patches only with -patchshadows)
    const occ=!(te.f&(TF_SKY|TF_ALPHATEST))&&!((te.cf|0)&CONTENTS_TRANSLUCENT)&&k!==1;
    LT.units.push({i0:u.i0,n:u.n,k:k,mn:mn,mx:mx,lm:lmOn&&!(te.f&TF_SKY),vtx:vtx,occ:occ});
  });
  for(let v=0;v<nv;v++){const l=Math.hypot(N[v*4],N[v*4+1],N[v*4+2])||1;N[v*4]/=l;N[v*4+1]/=l;N[v*4+2]/=l;N[v*4+3]=side[v];}
  LT.lnrm=N;
  // and the solid brushes, every side (caulk too): q3map's trace stops in the tree's solid
  // leafs before it looks at surfaces (TraceLine_r). Not the sky's: the sun's trace that
  // ends in a sky brush is the sun seen (SunToPoint), and no light is beyond them.
  LT.sb=[];
  for(const p of SC.prims){
    if(p.kind!==0||!WORLDLIKE[MAP.ents[p.ent].cls]||!isFinite(p.mins[0]))continue;
    const pr=MAP.ents[p.ent].prims[p.bn];if(!pr||!pr.d||!pr.d.faces.length)continue;
    const f0=pr.d.faces[0],te=texFor(f0.tex);
    if(LT.structOnly&&(MAP.ents[p.ent].cls==='detail'||pr.d.faces.some(f=>(f.cont|0)&CONTENTS_DETAIL)))continue;
    let c=(f0.cont|0)&~CONTENTS_DETAIL;if(!c)c=(te.cf|0)|((te.p||[]).some(x=>CLEARS_SOLID.has(x))?0:1);
    if(!(c&1))continue;
    if(pr.d.faces.some(f=>((f.flags|0)&4)||(texFor(f.tex).f&TF_SKY)))continue;
    const tri=[];for(let f=p.f0;f<p.f1;f++)for(let q=SC.faceI0[f];q<SC.faceI0[f]+SC.faceIN[f];q++)tri.push(SC.tri[q]);
    if(tri.length)LT.sb.push({mn:p.mins,mx:p.maxs,t:new Uint32Array(tri)});
  }
  // the map's size, for the sun and sky maps
  const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  for(let v=0;v<nv;v++)for(let j=0;j<3;j++){const x=P[v*3+j];if(x<mn[j])mn[j]=x;if(x>mx[j])mx[j]=x;}
  LT.ctr=[(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2];LT.rad=Math.max(64,Math.hypot(mx[0]-mn[0],mx[1]-mn[1],mx[2]-mn[2])/2+64);
  // ---- probes: the props' vertices (in their baked light's order), vertex-lit polygons'
  // vertices, then one per model lit by the light grid
  const L=D.lit, pp=[],pn=[],pb=[],world=[];
  const smn=L.sm!=null?(L.smn|0):0;
  for(let i=0;i<smn;i++){pp.push(0,0,0);pn.push(0,0,1,-2);}         // filled below (-2: unused)
  const smb=smn?D.bytes(L.sm):null;
  for(let i=0;i<smn;i++)pb.push(smb[i*3],smb[i*3+1],smb[i*3+2],255);
  if(smn&&L.st)for(const R of MODELS){
    if(!R.eng)continue;
    // the model's vertex normals, from its triangles
    const nn=new Float32Array(R.pos.length);
    for(let q=0;q+2<R.idx.length;q+=3){const a=R.idx[q]*3,b=R.idx[q+1]*3,c=R.idx[q+2]*3;
      const e1=[R.pos[b]-R.pos[a],R.pos[b+1]-R.pos[a+1],R.pos[b+2]-R.pos[a+2]],e2=[R.pos[c]-R.pos[a],R.pos[c+1]-R.pos[a+1],R.pos[c+2]-R.pos[a+2]];
      const f=vcross(e1,e2);for(const v of [a,b,c]){nn[v]+=f[0];nn[v+1]+=f[1];nn[v+2]+=f[2];}}
    for(const ei of R.inst){const base=L.st[ei];if(base==null)continue;
      const rows=instRows(ENTS[ei]);
      for(let k=0;k<R.eng.length;k++){const slot=base+R.eng[k];if(slot<0||slot>=smn||pn[slot*4+3]!==-2)continue;
        const x=R.pos[k*3],y=R.pos[k*3+1],z=R.pos[k*3+2];
        pp[slot*3]=rows[0]*x+rows[1]*y+rows[2]*z+rows[3];pp[slot*3+1]=rows[4]*x+rows[5]*y+rows[6]*z+rows[7];pp[slot*3+2]=rows[8]*x+rows[9]*y+rows[10]*z+rows[11];
        const a=nn[k*3],b=nn[k*3+1],c=nn[k*3+2];
        let w=[rows[0]*a+rows[1]*b+rows[2]*c,rows[4]*a+rows[5]*b+rows[6]*c,rows[8]*a+rows[9]*b+rows[10]*c];
        w=vnorm(w)||[0,0,1];pn[slot*4]=w[0];pn[slot*4+1]=w[1];pn[slot*4+2]=w[2];pn[slot*4+3]=1;}}}
  for(let i=0;i<smn;i++)world.push(pn[i*4+3]!==-2);
  // vertex-lit polygons' vertices
  const vslot=new Float32Array(nv).fill(-1);
  for(const u of LT.units){if(!u.vtx)continue;
    for(let q=0;q<u.n;q++){const v=T[u.i0+q];if(vslot[v]>=0||LM[v*3+2]>-0.5||LM[v*3+2]<-1.5)continue;
      vslot[v]=pp.length/3;pp.push(P[v*3],P[v*3+1],P[v*3+2]);pn.push(N[v*4],N[v*4+1],N[v*4+2],N[v*4+3]);
      pb.push(LIT.col[v*4],LIT.col[v*4+1],LIT.col[v*4+2],255);world.push(true);}}
  LT.vslot=vslot;
  // models lit by the light grid: their origin, lit from every side
  LT.entSlot=new Map();
  if(L.el)for(const R of MODELS)for(const ei of R.inst){const g=L.el[ei],X=ENTS[ei];if(!g||!X||!X.origin||LT.entSlot.has(ei))continue;
    LT.entSlot.set(ei,pp.length/3);pp.push(X.origin[0],X.origin[1],X.origin[2]);pn.push(0,0,0,-1);pb.push(g[0],g[1],g[2],255);world.push(false);}
  LT.np=pp.length/3;LT.ph=Math.max(1,Math.ceil(LT.np/LT_PW));
  LT.ppos=new Float32Array(pp);LT.pworld=world;
  // a grid of the probes by 512-unit cells, to find the ones a light reaches
  LT.pgrid=new Map();
  for(let i=0;i<LT.np;i++){if(pn[i*4+3]===-2)continue;const k=ltCell(pp[i*3],pp[i*3+1],pp[i*3+2]);let a=LT.pgrid.get(k);if(!a){a=[];LT.pgrid.set(k,a);}a.push(i);}
  // ---- GL: programs, buffers, textures
  LT.Pd=compile(VS_LTD,FS_LTD);LT.Plm=compile(VS_LTLM,FS_LTW);LT.Ppr=compile(VS_LTPR,FS_LTW);
  LT.Pcov=compile(VS_LTLM,FS_LTCOV);LT.Prel=compile(VS_LTQ,FS_LTREL);LT.Pprel=compile(VS_LTQ,FS_LTPREL);
  LT.bN=makeBuf(gl.ARRAY_BUFFER,N);LT.ib=gl.createBuffer();LT.sib=gl.createBuffer();
  LT.vSB=gl.createVertexArray();gl.bindVertexArray(LT.vSB);attr(0,B.pos,3);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.sib);gl.bindVertexArray(null);
  LT.vLM=gl.createVertexArray();gl.bindVertexArray(LT.vLM);attr(0,B.lPos,3);attr(8,B.lLM,3);attr(13,LT.bN,4);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.ib);gl.bindVertexArray(null);
  const slots=new Float32Array(LT.np);for(let i=0;i<LT.np;i++)slots[i]=i;
  LT.bPP=makeBuf(gl.ARRAY_BUFFER,LT.ppos);LT.bPN=makeBuf(gl.ARRAY_BUFFER,new Float32Array(pn));LT.bPS=makeBuf(gl.ARRAY_BUFFER,slots);LT.pib=gl.createBuffer();
  LT.vPR=gl.createVertexArray();gl.bindVertexArray(LT.vPR);attr(0,LT.bPP,3);attr(13,LT.bPN,4);attr(14,LT.bPS,1);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.pib);gl.bindVertexArray(null);
  // the vertex-lit polygons read their relit light at their slot (VS_LIT's aVP)
  LT.bVS=makeBuf(gl.ARRAY_BUFFER,vslot);gl.bindVertexArray(B.vLit);attr(13,LT.bVS,1);gl.bindVertexArray(null);
  // the lightmap pages' atlas, 8 pages across
  LT.cols=Math.min(8,B.lmN);LT.aw=LT.cols*128;LT.ah=Math.ceil(B.lmN/LT.cols)*128;
  const f16=(w,h)=>ltTex(w,h,gl.RGBA16F,gl.RGBA,gl.HALF_FLOAT,gl.NEAREST);
  LT.tTot=f16(LT.aw,LT.ah);LT.tOff=f16(LT.aw,LT.ah);LT.tSun=f16(LT.aw,LT.ah);LT.tCov=ltTex(LT.aw,LT.ah,gl.RGBA8,gl.RGBA,gl.UNSIGNED_BYTE,gl.NEAREST);
  LT.fTot=ltFB(LT.tTot);LT.fOff=ltFB(LT.tOff);LT.fSun=ltFB(LT.tSun);LT.fCov=ltFB(LT.tCov);
  LT.pTot=f16(LT_PW,LT.ph);LT.pOff=f16(LT_PW,LT.ph);LT.pSun=f16(LT_PW,LT.ph);
  LT.fpTot=ltFB(LT.pTot);LT.fpOff=ltFB(LT.pOff);LT.fpSun=ltFB(LT.pSun);
  const bake=new Uint8Array(LT_PW*LT.ph*4);bake.set(pb);
  LT.pBake=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,LT.pBake);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,LT_PW,LT.ph,0,gl.RGBA,gl.UNSIGNED_BYTE,bake);
  for(const p of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,p,gl.NEAREST);
  LT.pOut=ltTex(LT_PW,LT.ph,gl.RGBA8,gl.RGBA,gl.UNSIGNED_BYTE,gl.NEAREST);LT.fpOut=ltFB(LT.pOut);
  // the relit lightmap pages, as B.lmTex holds them
  LT.lmOut=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D_ARRAY,LT.lmOut);gl.texStorage3D(gl.TEXTURE_2D_ARRAY,1,gl.RGBA8,128,128,B.lmN);
  for(const[p,v]of[[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D_ARRAY,p,v);
  LT.fLM=gl.createFramebuffer();
  // distance maps: the cube's six faces in one texture, a sun / sky map
  LT.tCube=ltTex(LT_CUBE*3,LT_CUBE*2,gl.R32F,gl.RED,gl.FLOAT,gl.NEAREST);
  LT.rCube=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,LT.rCube);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT24,LT_CUBE*3,LT_CUBE*2);
  LT.fCube=ltFB(LT.tCube,LT.rCube);
  LT.tDir=ltTex(LT_DIR,LT_DIR,gl.R32F,gl.RED,gl.FLOAT,gl.NEAREST);
  LT.rDir=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,LT.rDir);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT24,LT_DIR,LT_DIR);
  LT.fDir=ltFB(LT.tDir,LT.rDir);
  LT.bQ=makeBuf(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]));
  LT.vQ=gl.createVertexArray();gl.bindVertexArray(LT.vQ);attr(0,LT.bQ,2);gl.bindVertexArray(null);
  for(const f of [LT.fTot,LT.fOff,LT.fSun,LT.fCov,LT.fpTot,LT.fpOff,LT.fpSun])ltClear(f);
  // the world's ambient light (ambientlight, whole numbers as the compiler floors it),
  // brightened as the baked light is
  const wk=MAP.ents[0]?MAP.ents[0]:{kv:[]}, am=ltVec(ltKey(wk,'ambientlight'))||[0,0,0], sh=1<<(L.shift|0);
  LT.amb=am.map(x=>Math.min(255,Math.max(0,Math.floor(x))*sh)/255);
  LT.prepped=true;
}
function ltCell(x,y,z){return Math.floor(x/512)+','+Math.floor(y/512)+','+Math.floor(z/512);}
function ltClear(f){gl.bindFramebuffer(gl.FRAMEBUFFER,f);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);}
// the triangles of the units a sphere reaches (lightmapped ones or occluders), as indices
function ltIdx(o,R,want){
  const parts=[];let n=0;
  for(const u of LT.units){if(!u[want])continue;
    if(o[0]+R<u.mn[0]||o[0]-R>u.mx[0]||o[1]+R<u.mn[1]||o[1]-R>u.mx[1]||o[2]+R<u.mn[2]||o[2]-R>u.mx[2])continue;
    parts.push(u);n+=u.n;}
  const out=new Uint32Array(n);let k=0;
  for(const u of parts){
    if(u.k===1){for(let q=0;q<u.n;q+=12){out.set(LIT.tri.subarray(u.i0+q,u.i0+Math.min(u.n,q+6)),k);k+=Math.min(6,u.n-q);}}
    else{out.set(LIT.tri.subarray(u.i0,u.i0+u.n),k);k+=u.n;}}
  return out.subarray(0,k);}
function ltProbeIdx(o,R,world){
  const out=[],c0=[Math.floor((o[0]-R)/512),Math.floor((o[1]-R)/512),Math.floor((o[2]-R)/512)],c1=[Math.floor((o[0]+R)/512),Math.floor((o[1]+R)/512),Math.floor((o[2]+R)/512)];
  for(let x=c0[0];x<=c1[0];x++)for(let y=c0[1];y<=c1[1];y++)for(let z=c0[2];z<=c1[2];z++){
    const a=LT.pgrid.get(x+','+y+','+z);if(!a)continue;
    for(const i of a){if(LT.pworld[i]!==world)continue;const P=LT.ppos;
      if((P[i*3]-o[0])**2+(P[i*3+1]-o[1])**2+(P[i*3+2]-o[2])**2<=R*R)out.push(i);}}
  return new Uint32Array(out);}
// one light's distance cube, of the drawn surfaces it reaches
function ltCube(l){
  const idx=ltIdx(l.o,l.R,'occ'), sb=ltSolidIdx(l.o,l.R);
  gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fCube);gl.viewport(0,0,LT_CUBE*3,LT_CUBE*2);gl.depthMask(true);
  gl.clearBufferfv(gl.COLOR,0,new Float32Array([1e9,0,0,0]));gl.clearDepth(1);gl.clear(gl.DEPTH_BUFFER_BIT);
  LT.fv=[];
  const Pm=ltPersp(1,l.R+32);
  for(let f=0;f<6;f++)LT.fv.push(new Float32Array(mul4(Pm,ltLook(l.o,LT_FACES[f][0],LT_FACES[f][1]))));
  gl.useProgram(LT.Pd);gl.uniform4f(LT.Pd.u.uL,l.o[0],l.o[1],l.o[2],0);
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.depthMask(true);gl.disable(gl.CULL_FACE);gl.disable(gl.BLEND);
  ltDrawOcc(idx,sb,f=>{gl.viewport((f%3)*LT_CUBE,Math.floor(f/3)*LT_CUBE,LT_CUBE,LT_CUBE);gl.uniformMatrix4fv(LT.Pd.u.uVP,false,LT.fv[f]);},6);
}
// the structural brushes' triangles a sphere reaches
function ltSolidIdx(o,R){
  let n=0;const parts=[];
  for(const b of LT.sb){if(o[0]+R<b.mn[0]||o[0]-R>b.mx[0]||o[1]+R<b.mn[1]||o[1]-R>b.mx[1]||o[2]+R<b.mn[2]||o[2]-R>b.mx[2])continue;parts.push(b.t);n+=b.t.length;}
  const out=new Uint32Array(n);let k=0;for(const t of parts){out.set(t,k);k+=t.length;}return out;}
// draw the occluders (the drawn surfaces, then the structural brushes) once per view
function ltDrawOcc(idx,sb,view,nv){
  if(idx.length){gl.bindVertexArray(LT.vLM);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STREAM_DRAW);
    for(let f=0;f<nv;f++){view(f);gl.drawElements(gl.TRIANGLES,idx.length,gl.UNSIGNED_INT,0);}}
  if(sb.length){gl.bindVertexArray(LT.vSB);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.sib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,sb,gl.STREAM_DRAW);
    for(let f=0;f<nv;f++){view(f);gl.drawElements(gl.TRIANGLES,sb.length,gl.UNSIGNED_INT,0);}}
  gl.bindVertexArray(null);
}
// add (sign 1) or take out (-1) one light's weights: lightmap texels into fLm, probes into fPr
function ltWeigh(l,fLm,fPr,sign){
  ltCube(l);
  const set=P=>{gl.useProgram(P);gl.uniform1i(P.u.uKind,0);gl.uniform4f(P.u.uL,l.o[0],l.o[1],l.o[2],l.ph);
    gl.uniform4f(P.u.uC,l.c[0],l.c[1],l.c[2],l.R);
    gl.uniform4f(P.u.uS,l.dir?l.dir[0]:0,l.dir?l.dir[1]:0,l.dir?l.dir[2]:0,l.dir?l.rbd:0);
    gl.uniform4f(P.u.uF,l.lin?1:0,l.fall,LT.lam,0);
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,LT.tCube);gl.uniform1i(P.u.uSh,0);gl.uniform1f(P.u.uSz,LT_CUBE);
    gl.uniformMatrix4fv(P.u['uFV[0]'],false,new Float32Array([].concat(...LT.fv.map(m=>Array.from(m)))));};
  gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);
  gl.blendEquation(sign<0?gl.FUNC_REVERSE_SUBTRACT:gl.FUNC_ADD);
  if(l.world){const idx=ltIdx(l.o,l.R,'lm');
    if(idx.length){gl.bindFramebuffer(gl.FRAMEBUFFER,fLm);gl.viewport(0,0,LT.aw,LT.ah);set(LT.Plm);
      gl.uniform3f(LT.Plm.u.uAt,LT.cols,128/LT.aw,128/LT.ah);
      gl.bindVertexArray(LT.vLM);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STREAM_DRAW);
      gl.drawElements(gl.TRIANGLES,idx.length,gl.UNSIGNED_INT,0);}}
  for(const world of [true,false]){if(world?!l.world:!l.ents)continue;
    const pi=ltProbeIdx(l.o,l.R,world);if(!pi.length)continue;
    gl.bindFramebuffer(gl.FRAMEBUFFER,fPr);gl.viewport(0,0,LT_PW,LT.ph);set(LT.Ppr);gl.uniform2f(LT.Ppr.u.uPA,LT_PW,LT.ph);
    gl.bindVertexArray(LT.vPR);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.pib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,pi,gl.STREAM_DRAW);
    gl.drawElements(gl.POINTS,pi.length,gl.UNSIGNED_INT,0);}
  gl.blendEquation(gl.FUNC_ADD);gl.disable(gl.BLEND);gl.depthMask(true);gl.bindVertexArray(null);gl.bindFramebuffer(gl.FRAMEBUFFER,null);
}
// The sun's weights, on a map with sky and a sun: straight sunlight (suncolor, the angle
// to the sun, a shadow map toward it) and the sky's (sundiffuse x sundiffusecolor, the
// sky seen from 16 directions, each through its own shadow map)
// whether the .bsp has sky polygons at all (LIT.sky holds only the ones shown)
function ltHasSky(){return !!LIT&&LIT.units.some(u=>u.n&&((TEX[u.ti]||{}).f&TF_SKY));}
function ltSunDirs(){
  const wk=MAP.ents[0]||{kv:[]}, sd=ltVec(ltKey(wk,'sundirection'));
  const sc=ltVec(ltKey(wk,'suncolor'))||ltVec(ltKey(wk,'sunlight'));
  if(!ltHasSky()||(!sd&&!sc))return [];
  const col=sc||[0,0,0], out=[];
  if(sd)out.push([ltForward(sd),col]);
  const diff=ltNum(ltKey(wk,'sundiffuse'),1), dc=ltVec(ltKey(wk,'sundiffusecolor'))||col, dirs=[];
  for(const[el,n]of[[90,1],[60,5],[30,10]])for(let k=0;k<n;k++){const e=el*Math.PI/180,a=(k/n)*2*Math.PI+(el===60?0.3:0);dirs.push([Math.cos(e)*Math.cos(a),Math.cos(e)*Math.sin(a),Math.sin(e)]);}
  const wsum=dirs.reduce((s,d)=>s+d[2],0);
  for(const d of dirs)out.push([d,dc.map(x=>x*diff/wsum)]);
  return out;
}
function ltSun(dir,col){
  // the drawn surfaces seen from far toward dir, keeping how far toward it the nearest is
  const e=[LT.ctr[0]+dir[0]*LT.rad,LT.ctr[1]+dir[1]*LT.rad,LT.ctr[2]+dir[2]*LT.rad];
  const f=[-dir[0],-dir[1],-dir[2]], up=Math.abs(f[2])>0.9?[1,0,0]:[0,0,1];
  const VP=new Float32Array(mul4(ltOrtho(LT.rad,0,LT.rad*2),ltLook(e,f,up)));
  if(!LT.occAll){LT.occAll=ltIdx(LT.ctr,1e9,'occ');LT.sbAll=ltSolidIdx(LT.ctr,1e9);}
  gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fDir);gl.viewport(0,0,LT_DIR,LT_DIR);gl.depthMask(true);
  gl.clearBufferfv(gl.COLOR,0,new Float32Array([-1e9,0,0,0]));gl.clearDepth(1);gl.clear(gl.DEPTH_BUFFER_BIT);
  gl.useProgram(LT.Pd);gl.uniform4f(LT.Pd.u.uL,dir[0],dir[1],dir[2],1);gl.uniformMatrix4fv(LT.Pd.u.uVP,false,VP);
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.depthMask(true);gl.disable(gl.CULL_FACE);gl.disable(gl.BLEND);
  ltDrawOcc(LT.occAll,LT.sbAll,()=>{},1);
  const set=P=>{gl.useProgram(P);gl.uniform1i(P.u.uKind,1);gl.uniform4f(P.u.uL,dir[0],dir[1],dir[2],0);gl.uniform4f(P.u.uC,col[0],col[1],col[2],0);
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,LT.tDir);gl.uniform1i(P.u.uSh,0);gl.uniform1f(P.u.uSz,LT_DIR);
    gl.uniformMatrix4fv(P.u['uFV[0]'],false,VP);};
  gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);gl.blendEquation(gl.FUNC_ADD);
  const li=ltIdx(LT.ctr,1e9,'lm');
  if(li.length){gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fSun);gl.viewport(0,0,LT.aw,LT.ah);set(LT.Plm);gl.uniform3f(LT.Plm.u.uAt,LT.cols,128/LT.aw,128/LT.ah);
    gl.bindVertexArray(LT.vLM);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,li,gl.STREAM_DRAW);
    gl.drawElements(gl.TRIANGLES,li.length,gl.UNSIGNED_INT,0);}
  if(LT.np){const all=new Uint32Array(LT.np);for(let i=0;i<LT.np;i++)all[i]=i;
    gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fpSun);gl.viewport(0,0,LT_PW,LT.ph);set(LT.Ppr);gl.uniform2f(LT.Ppr.u.uPA,LT_PW,LT.ph);
    gl.bindVertexArray(LT.vPR);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.pib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,all,gl.STREAM_DRAW);
    gl.drawElements(gl.POINTS,LT.np,gl.UNSIGNED_INT,0);}
  gl.disable(gl.BLEND);gl.depthMask(true);gl.bindVertexArray(null);gl.bindFramebuffer(gl.FRAMEBUFFER,null);
}
function ltCoverage(){
  const idx=ltIdx(LT.ctr,1e9,'lm');
  gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fCov);gl.viewport(0,0,LT.aw,LT.ah);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
  gl.useProgram(LT.Pcov);gl.uniform3f(LT.Pcov.u.uAt,LT.cols,128/LT.aw,128/LT.ah);
  gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
  gl.bindVertexArray(LT.vLM);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,LT.ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STREAM_DRAW);
  if(idx.length)gl.drawElements(gl.TRIANGLES,idx.length,gl.UNSIGNED_INT,0);
  gl.bindVertexArray(null);gl.bindFramebuffer(gl.FRAMEBUFFER,null);
}
// copy the lights' total into the off texture (every light off) or clear it (all on)
function ltCopy(src,dst,w,h){gl.bindFramebuffer(gl.READ_FRAMEBUFFER,src);gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER,dst);
  gl.blitFramebuffer(0,0,w,h,0,0,w,h,gl.COLOR_BUFFER_BIT,gl.NEAREST);
  gl.bindFramebuffer(gl.READ_FRAMEBUFFER,null);gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER,null);}
// The relit lightmap pages, then the relit probes (the props' light, vertex light, the
// models' grid colours: each read at its slot while relit)
function ltCap(){return LT.kap*16*(1<<(D.lit.shift|0))/(255*LT.lam);}  // OFF to the pages' brightened units
// every light off and no sun (none, or turned off): only the ambient floor is left
function ltDark(){return (LT.nOff===LT.lights.length&&(!LT.sun.length||LT.sunOff))?1:0;}
function ltRelightPages(){
  gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
  gl.useProgram(LT.Prel);gl.bindVertexArray(LT.vQ);
  const tx=[[gl.TEXTURE_2D_ARRAY,B.lmTex,'uBake'],[gl.TEXTURE_2D,LT.tTot,'uTot'],[gl.TEXTURE_2D,LT.tOff,'uOff'],[gl.TEXTURE_2D,LT.tSun,'uSun'],[gl.TEXTURE_2D,LT.tCov,'uCov']];
  tx.forEach((t,k)=>{gl.activeTexture(gl.TEXTURE0+k);gl.bindTexture(t[0],t[1]);gl.uniform1i(LT.Prel.u[t[2]],k);});
  gl.uniform1i(LT.Prel.u.uCols,LT.cols);gl.uniform3f(LT.Prel.u.uA,LT.amb[0],LT.amb[1],LT.amb[2]);gl.uniform1i(LT.Prel.u.uDark,ltDark());gl.uniform1f(LT.Prel.u.uCap,ltCap());
  gl.uniform1i(LT.Prel.u.uSunOn,LT.sunOff?0:1);
  gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fLM);gl.viewport(0,0,128,128);
  for(let k=0;k<B.lmN;k++){gl.framebufferTextureLayer(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,LT.lmOut,0,k);
    gl.uniform1i(LT.Prel.u.uLayer,k);gl.drawArrays(gl.TRIANGLES,0,3);}
  ltUnbind(5);
}
function ltRelightProbes(){
  if(!LT.np)return;
  gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
  gl.useProgram(LT.Pprel);gl.bindVertexArray(LT.vQ);
  const pt=[[LT.pBake,'uBake'],[LT.pTot,'uTot'],[LT.pOff,'uOff'],[LT.pSun,'uSun']];
  pt.forEach((t,k)=>{gl.activeTexture(gl.TEXTURE0+k);gl.bindTexture(gl.TEXTURE_2D,t[0]);gl.uniform1i(LT.Pprel.u[t[1]],k);});
  gl.uniform3f(LT.Pprel.u.uA,LT.amb[0],LT.amb[1],LT.amb[2]);gl.uniform1i(LT.Pprel.u.uDark,ltDark());gl.uniform1f(LT.Pprel.u.uCap,ltCap());
  gl.uniform1i(LT.Pprel.u.uSunOn,LT.sunOff?0:1);
  gl.bindFramebuffer(gl.FRAMEBUFFER,LT.fpOut);gl.viewport(0,0,LT_PW,LT.ph);gl.drawArrays(gl.TRIANGLES,0,3);
  ltUnbind(4);
}
function ltUnbind(n){
  for(let k=0;k<n;k++){gl.activeTexture(gl.TEXTURE0+k);gl.bindTexture(gl.TEXTURE_2D,null);gl.bindTexture(gl.TEXTURE_2D_ARRAY,null);}
  gl.activeTexture(gl.TEXTURE0);gl.bindVertexArray(null);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.depthMask(true);
}

// ---- the work, a little each frame -------------------------------------------------------
// A few steps at a time, the next ones only once the graphics card has finished the last
// (a fence), so no frame hands it a long run of work. The steps under way are noted in the
// browser's storage, and the note dropped once the result has been drawn: if the graphics
// driver resets meanwhile, the note says where, and the next press on this map only warns.
const LT_CRUMB='mohaa-map-lights-step';
function ltCrumb(step){try{if(step==null)localStorage.removeItem(LT_CRUMB);
  else localStorage.setItem(LT_CRUMB,JSON.stringify({page:document.title,step:step,t:Date.now()}));}catch(e){}}
function ltCrumbRead(){try{const v=JSON.parse(localStorage.getItem(LT_CRUMB)||'null');return v&&v.page===document.title&&v.step?v:null;}catch(e){return null;}}
// a line for the launcher's Output pane (in a browser: the page's console)
function hostLog(tag,msg){
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-log\n'+tag+'\n'+String(msg).replace(/\n/g,' '));return;}}catch(_e){}
  try{console.log(msg);}catch(_e){}
}
function ltStep(label,fn){fn.label=label;return fn;}
function ltProgress(msg){const h=$('hintHover');clearTimeout(_flashT);h.textContent=msg;h.style.color='var(--accent)';}
function ltRun(){
  if(gl.isContextLost()){LT.queue=[];LT.busy=false;return;}
  if(LT.fence){
    if(gl.getSyncParameter(LT.fence,gl.SYNC_STATUS)!==gl.SIGNALED){requestAnimationFrame(ltRun);return;}
    gl.deleteSync(LT.fence);LT.fence=null;}
  if(!LT.queue.length){
    LT.busy=false;
    if(LT.want){ltApply();return;}  // a change asked for while this one was worked out
    // drop the note once the new light has been drawn for a moment
    clearTimeout(LT.settleT);LT.settleT=setTimeout(()=>{if(!gl.isContextLost()&&!LT.busy){ltCrumb(null);LT.step='';}},1200);
    return;}
  // the note names every step of the batch: the card runs them together
  const t0=performance.now(),names=[];let k=0;
  try{
    while(LT.queue.length&&k<LT.batch&&(k===0||performance.now()-t0<12)){
      const f=LT.queue.shift();if(f.label){names.push(f.label);LT.step=names.join(' + ');ltCrumb(LT.step);}f();k++;}
  }catch(e){console.error(e);LT.queue=[];LT.busy=false;flash('Turning lights off failed: '+(e&&e.message||e));return;}
  LT.fence=gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE,0);gl.flush();
  requestAnimationFrame(ltRun);
}
// Bring the baked light in line with LT.off: work out the totals the first time, then add
// or take out the lights whose state changed (or start from all / none).
function ltApply(){
  if(!ltCheck())return;
  if(LT.busy){LT.want=true;return;}
  LT.want=false;LT.busy=true;clearTimeout(LT.settleT);
  const q=LT.queue;
  if(!LT.prepped){ltCrumb('getting ready (shaders, textures)');ltPrep();}
  if(!B.lmN){LT.busy=false;flash('The lightmaps are still loading - try again in a moment');return;}
  const n=LT.lights.length;
  if(!LT.totReady){
    // the first time takes a few seconds on a slower PC: say so in the launcher's Output
    const t0=performance.now(),what=LT.what==='sun'?'Sun light':'Lights off';
    hostLog('dim',what+': working out how much of the baked light each of the '+n+' lights and the sun gave (the first time takes a few seconds)...');
    LT.firstLog=()=>hostLog('ok',what+': ready in '+((performance.now()-t0)/1000).toFixed(1)+' s');
    q.push(ltStep('clearing the sums, the lightmaps\' coverage',()=>{ltClear(LT.fTot);ltClear(LT.fpTot);ltClear(LT.fSun);ltClear(LT.fpSun);ltClear(LT.fOff);ltClear(LT.fpOff);LT.applied.fill(0);ltCoverage();}));
    LT.lights.forEach((l,i)=>q.push(ltStep('light '+(i+1)+' of '+n+' (entity '+l.ei+')',()=>{ltProgress('Working out the map\'s lights: '+(i+1)+' of '+n);ltWeigh(l,LT.fTot,LT.fpTot,1);})));
    LT.sun=ltSunDirs();
    LT.sun.forEach((s,k)=>q.push(ltStep('sunlight '+(k+1)+' of '+LT.sun.length,()=>{ltProgress('Working out the sunlight: '+(k+1)+' of '+LT.sun.length);ltSun(s[0],s[1]);})));
    q.push(()=>{LT.totReady=true;});
  }
  q.push(()=>{
    const off=LT.off, ap=LT.applied;let nOff=0,diff=0;
    for(let i=0;i<n;i++){nOff+=off[i];if(off[i]!==ap[i])diff++;}
    const steps=[];
    if(nOff===n&&diff){steps.push(ltStep('every light off: copying the sums',()=>{ltCopy(LT.fTot,LT.fOff,LT.aw,LT.ah);ltCopy(LT.fpTot,LT.fpOff,LT_PW,LT.ph);ap.fill(1);}));}
    else if(nOff===0&&diff){steps.push(ltStep('every light on: clearing the sums',()=>{ltClear(LT.fOff);ltClear(LT.fpOff);ap.fill(0);}));}
    else{let k=0;for(let i=0;i<n;i++)if(off[i]!==ap[i]){const sign=off[i]?1:-1,j=++k;
      steps.push(ltStep('turning light '+(i+1)+' (entity '+LT.lights[i].ei+') '+(sign>0?'off':'on'),()=>{if(diff>3)ltProgress('Turning lights '+(sign>0?'off':'on')+': '+j+' of '+diff);ltWeigh(LT.lights[i],LT.fOff,LT.fpOff,sign);ap[i]=off[i];}));}}
    steps.push(ltStep('relighting the lightmap pages',()=>{LT.nOff=nOff;ltRelightPages();}));
    steps.push(ltStep('relighting the props, vertex light and models',()=>{ltRelightProbes();}));
    steps.push(ltStep('drawing the map with the new light',()=>{LT.active=nOff>0||LT.sunOff;rebuildModels();ltDone();}));
    q.unshift(...steps);
  });
  requestAnimationFrame(ltRun);
}
function ltDone(){
  const n=LT.lights.length;
  if(LT.firstLog){LT.firstLog();LT.firstLog=null;}
  syncButtons();updateSelPanel();requestDraw();
  if(LT.what==='sun')flash(LT.sunOff?'Sun light off: '+(LT.nOff===n?'only the ambient light is left':'the map lit by its lights alone')
    :'Sun light on: the sun and the sky light the map again');
  else flash(LT.nOff===0?'Every light is on'+(LT.sunOff?' (the sun is still off)':': the map as the game lights it')
    :LT.nOff===n?'Every light is off'+(LT.sunHas&&!LT.sunOff?' (the sun and the sky still light the map)':''):LT.nOff+' of '+n+' lights off');
  if(fullBright)setTimeout(()=>flash('Full Brightness is on: turn it off (B) to see the game\'s light'),1700);
}
// After a graphics driver reset on this map, the first press only says so; another within
// six seconds goes ahead, a step at a time.
function ltMayRun(){
  if(!LT.crash)return true;
  const now=performance.now();
  if(LT.crashArm&&now-LT.crashArm<6000){LT.crash=null;LT.crashArm=0;LT.batch=1;syncButtons();return true;}
  LT.crashArm=now;
  flash('The last time lights were turned off on this map, the graphics driver reset ('+LT.crash.step+'). Press again within 6 seconds to try anyway.');
  return false;
}
// Display: Lights off. With any light still on, every light goes off; else all come back on.
function toggleLightsOff(){
  if(!ltCheck()){flash(LT.why);return;}
  if(!ltMayRun())return;
  const all=LT.off.every(x=>x);LT.off.fill(all?0:1);LT.what='lights';ltApply();
}
// Display: Sun light. Off takes the sun's and the sky's light out of the baked light.
function toggleSunLight(){
  if(!ltCheck()){flash(LT.why);return;}
  if(!LT.sunHas){flash(LT.sunWhy);return;}
  if(!ltMayRun())return;
  LT.sunOff=!LT.sunOff;LT.what='sun';ltApply();
}
// Selection: Turn off / Turn on the selected lights
function setSelLights(on){
  if(!ltCheck()){flash(LT.why);return;}
  let k=0;const want=[];for(const ei of selectedEnts()){const i=LT.byEnt.get(ei);if(i==null)continue;
    // every light entity at that index (a light written twice shares it)
    LT.lights.forEach((l,j)=>{if(l.ei===ei&&LT.off[j]!==(on?0:1))want.push(j);});}
  if(!want.length){flash(on?'The selected lights are already on':'The selected lights are already off');return;}
  if(!ltMayRun())return;
  for(const j of want){LT.off[j]=on?0:1;k++;}
  LT.what='lights';ltApply();
}
function draw(){
  if(!gl||!SC)return;
  FRAMES++;skyQueryPoll();
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  gl.viewport(0,0,glcv.width,glcv.height);
  // with the map's fog on, everything past the fog's far end is fog colour, as in game
  // a lightning flash (r_fastsky 1): no sky, cleared to the fog colour where there is a
  // farplane, else to 0.5 0.5 1 (RB_BeginDrawingView)
  const bg=THU.flash&&!simpleSky?((FOG.far>0||farOverride())?fogCol():[0.5,0.5,1]):fogOn()?fogCol():TH.bg;
  gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  VP=viewProj(null);
  updateInside(false);
  cullModels(frustumOf(VP));
  drawScene(VP,0);
  drawShowSky(VP);
  drawSunFlare(VP);
  drawSelection(VP);
  drawLines(VP);
  drawOutlines(VP);
  drawShowTris(VP);
  drawShowNormals(VP);
  drawRoutes(VP);
  drawGrid(VP);
  drawScriptTrigs(VP);
  drawModify(VP);
  drawSim(VP);
  if(CVARS.r_light_showgrid)drawLightGrid(VP);
  drawCvarLines(VP);
  draw2D();
  // the text read-outs: a few times a second while the view moves (a DOM change each frame
  // costs a layout), and once more when it stops
  textSoon();
  cloudTick();
}
// ---- view culling --------------------------------------------------------------------------
// Only what can be seen is sent to the graphics card. The world's faces (and the game's
// polygons) are sorted, within each texture's run, by the 1024-unit cell they lie in, and a
// cell's part of a run is skipped when its box is outside the view: off to a side or
// behind, past the far plane (the fog's or r_farplane's far end, the cubic clip), or outside
// the cubic clip's cube. Faces of brush entities (doors and exploder chunks move) are never
// skipped. Model instances are skipped by their bounding sphere (cullModels).
const CULL_CELL=1024;
const CULL={fk:null,fb:null,uk:null,ub:null};
let FR=null;                 // the frustum drawScene is drawing with (frustumOf)
// the six planes of a view-projection matrix, normalised (inside: a x + b y + c z + d >= 0)
function frustumOf(vp){
  const m=vp,P=[];
  for(const[r,sg]of[[0,1],[0,-1],[1,1],[1,-1],[2,1],[2,-1]]){
    const a=m[3]+sg*m[r],b=m[7]+sg*m[4+r],c=m[11]+sg*m[8+r],d=m[15]+sg*m[12+r],l=Math.hypot(a,b,c)||1;
    P.push([a/l,b/l,c/l,d/l]);}
  return{pl:P,clip:clipOn?clipDist:0,eye:[cam.pos[0],cam.pos[1],cam.pos[2]]};
}
function boxSeen(F,b,o){
  if(F.clip){const e=F.eye,c=F.clip;if(b[o]>e[0]+c||b[o+3]<e[0]-c||b[o+1]>e[1]+c||b[o+4]<e[1]-c||b[o+2]>e[2]+c||b[o+5]<e[2]-c)return false;}
  for(const p of F.pl){if(p[0]*(p[0]>=0?b[o+3]:b[o])+p[1]*(p[1]>=0?b[o+4]:b[o+1])+p[2]*(p[2]>=0?b[o+5]:b[o+2])+p[3]<0)return false;}
  return true;
}
function cullKey(mn,mx){
  const c=k=>Math.floor(((mn[k]+mx[k])/2+65536)/CULL_CELL)&127;
  return (c(2)*128+c(1))*128+c(0);
}
// each face's cell (-1: a brush entity's, never skipped) and box, from where the .map has it
function cullPrepFaces(){
  if(CULL.fk&&CULL.fk.length===SC.nf)return;
  const nf=SC.nf,K=new Int32Array(nf),Bb=new Float32Array(nf*6),P=SC.pos;
  for(let f=0;f<nf;f++){const ei=SC.faceEnt[f];
    const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(let v=SC.faceV0[f],ve=v+SC.faceVN[f];v<ve;v++)for(let k=0;k<3;k++){const w=P[v*3+k];if(w<mn[k])mn[k]=w;if(w>mx[k])mx[k]=w;}
    if(!isFinite(mn[0])||(ei>0&&!WORLDLIKE[MAP.ents[ei].cls])){K[f]=-1;Bb.set([-1e30,-1e30,-1e30,1e30,1e30,1e30],f*6);continue;}
    K[f]=cullKey(mn,mx);Bb.set([mn[0],mn[1],mn[2],mx[0],mx[1],mx[2]],f*6);}
  CULL.fk=K;CULL.fb=Bb;
}
// the same for the game's polygons, and each texture's list of them sorted by cell
function cullPrepLit(){
  if(CULL.uk&&CULL.uk.length===LIT.units.length)return;
  const U=LIT.units,K=new Int32Array(U.length),Bb=new Float32Array(U.length*6),P=LIT.pos,T=LIT.tri;
  U.forEach((u,k)=>{
    const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(let i=u.i0;i<u.i0+u.n;i++){const v=T[i]*3;for(let j=0;j<3;j++){const w=P[v+j];if(w<mn[j])mn[j]=w;if(w>mx[j])mx[j]=w;}}
    if(!isFinite(mn[0])||(u.ei>0&&!WORLDLIKE[MAP.ents[u.ei].cls])){K[k]=-1;Bb.set([-1e30,-1e30,-1e30,1e30,1e30,1e30],k*6);return;}
    K[k]=cullKey(mn,mx);Bb.set([mn[0],mn[1],mn[2],mx[0],mx[1],mx[2]],k*6);});
  CULL.uk=K;CULL.ub=Bb;
  for(const l of LIT.byTex.values())l.sort((a,b)=>K[a]-K[b]||a-b);
}
// a run's parts, one per cell, as its faces are added in cell order
function cullSegs(){
  const st=[],ct=[],bb=[];let key=null;
  return{add(k,B,o,at,n){
      if(k!==key||!st.length){key=k;st.push(at);ct.push(0);bb.push(Infinity,Infinity,Infinity,-Infinity,-Infinity,-Infinity);}
      const q=bb.length-6;ct[ct.length-1]+=n;
      for(let j=0;j<3;j++){if(B[o+j]<bb[q+j])bb[q+j]=B[o+j];if(B[o+3+j]>bb[q+3+j])bb[q+3+j]=B[o+3+j];}},
    done(){return st.length>1||(st.length===1&&bb[0]>-1e29)?{st:Int32Array.from(st),ct:Int32Array.from(ct),bb:Float32Array.from(bb)}:null;}};
}
// draw a run's parts that can be seen, joining neighbours (and small hidden gaps between
// them, so a run isn't cut into many tiny draws)
function drawRuns(op){
  const S=op.seg;
  if(!S||!FR){gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);return;}
  let a=-1,b=0,gap=0;
  for(let i=0;i<S.st.length;i++){
    if(boxSeen(FR,S.bb,i*6)){if(a<0)a=S.st[i];b=S.st[i]+S.ct[i];gap=0;}
    else if(a>=0){gap+=S.ct[i];if(gap>768){gl.drawElements(gl.TRIANGLES,b-a,gl.UNSIGNED_INT,a*4);a=-1;gap=0;}}
  }
  if(a>=0)gl.drawElements(gl.TRIANGLES,b-a,gl.UNSIGNED_INT,a*4);
}
// the model instances in view (their bounding spheres), packed into each model's buffer
function cullModels(F){
  for(const R of MODELS){
    const N=R.full|0;if(!N||!R.sph){continue;}
    const S=R.sph,A=R.all,O=R.stage;let n=0,same=!!R.vis&&R.vis.length===N;
    const vis=R.vis&&R.vis.length===N?R.vis:(R.vis=new Uint8Array(N));
    for(let i=0;i<N;i++){
      const x=S[i*4],y=S[i*4+1],z=S[i*4+2],r=S[i*4+3];let ok=true;
      if(F.clip){const e=F.eye,c=F.clip+r;if(Math.abs(x-e[0])>c||Math.abs(y-e[1])>c||Math.abs(z-e[2])>c)ok=false;}
      if(ok)for(const p of F.pl)if(p[0]*x+p[1]*y+p[2]*z+p[3]<-r){ok=false;break;}
      if(vis[i]!==(ok?1:0)){vis[i]=ok?1:0;same=false;}
      if(ok){O.set(A.subarray(i*INST_FLOATS,(i+1)*INST_FLOATS),n*INST_FLOATS);n++;}
    }
    if(same&&R.n===n)continue;
    R.n=n;
    // new storage rather than writing into the buffer the last frame may still be drawing
    // from (bufferSubData into a buffer in use can wait for the card)
    if(n){gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,O.subarray(0,n*INST_FLOATS),gl.DYNAMIC_DRAW);}
  }
}
// The selection: tinted red like MOHRadiant, plus an outline that shows through walls.
function drawSelection(vp){
  if(!selTriCount&&!markSelCount&&!MODELS.some(R=>R.nsel)&&!hovEdgeCount&&!hovBoxVerts)return;
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
  gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(-1,-2);gl.disable(gl.CULL_FACE);
  const sc=hexRGB(TH.sel);
  if(selTriCount){setCommon(PW,vp,2);gl.uniform4f(PW.u.uTint,sc[0],sc[1],sc[2],0.38);gl.bindVertexArray(B.vSel);
    gl.drawElements(gl.TRIANGLES,selTriCount,gl.UNSIGNED_INT,0);}
  if(markSelCount){setCommon(PC,vp,2);gl.uniform4f(PC.u.uTint,sc[0],sc[1],sc[2],0.5);gl.bindVertexArray(B.vMarkSel);
    gl.drawElements(gl.TRIANGLES,markSelCount,gl.UNSIGNED_INT,0);}
  // a model's tint follows what is drawn of it: its alpha-tested leaves, its sprite version
  setCommon(PM,vp,2);dvUniforms();gl.uniform4f(PM.u.uTint,sc[0],sc[1],sc[2],0.45);gl.uniform1i(PM.u.uLit,0);gl.uniform3fv(PM.u.uFwd,camAxes().f);
  for(const R of MODELS){if(!R.nsel)continue;gl.bindVertexArray(R.vaoSel);
    for(const s of R.surfs){if(!surfOn(R,s))continue;gl.uniform1i(PM.u.uAuto2,s.lod?1:0);bindMat(PM,s.ti,2);
      gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.nsel);}}
  gl.uniform1i(PM.u.uAuto2,0);gl.disable(gl.CULL_FACE);
  gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.bindVertexArray(null);gl.depthMask(true);gl.disable(gl.BLEND);gl.depthFunc(gl.LEQUAL);
}

// The selection's and the mouse-over's outlines, drawn after the lines so the Wire
// button's white edges don't cover them (the hovered brush's own edges are among those).
function drawOutlines(vp){
  if(!selEdgeCount&&!hovEdgeCount&&!hovBoxVerts)return;
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);gl.enable(gl.DEPTH_TEST);
  const sc=hexRGB(TH.sel);
  gl.useProgram(PL);gl.uniformMatrix4fv(PL.u.uVP,false,vp);
  if(selEdgeCount){
    gl.bindVertexArray(B.vSelE);gl.disableVertexAttribArray(7);gl.vertexAttrib4f(7,sc[0],sc[1],sc[2],1);
    if(view.xray){gl.depthFunc(gl.GREATER);gl.uniform1f(PL.u.uAlpha,0.35);gl.drawElements(gl.LINES,selEdgeCount,gl.UNSIGNED_INT,0);}
    gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,1);gl.drawElements(gl.LINES,selEdgeCount,gl.UNSIGNED_INT,0);
  }
  if(hovEdgeCount||hovBoxVerts){
    const hc=hexRGB(TH.accent);gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,view.wire?1:0.9);
    if(hovEdgeCount){gl.bindVertexArray(B.vHovE);gl.disableVertexAttribArray(7);gl.vertexAttrib4f(7,hc[0],hc[1],hc[2],1);
      gl.drawElements(gl.LINES,hovEdgeCount,gl.UNSIGNED_INT,0);}
    if(hovBoxVerts){gl.bindVertexArray(B.vHovBox);gl.vertexAttrib4f(7,hc[0],hc[1],hc[2],1);gl.drawArrays(gl.LINES,0,hovBoxVerts);}
  }
  gl.bindVertexArray(null);gl.depthMask(true);gl.disable(gl.BLEND);gl.depthFunc(gl.LEQUAL);
}

// ---- lines: wireframe, setsize boxes, target links, facing arrows ----------------------
function boxLines(L,mn,mx,c){
  const C=[];for(let k=0;k<8;k++)C.push([(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]]);
  boxLinesC(L,C,c);
}
// a box from its eight corners (corner k: bit 1 x, 2 y, 4 z at the max end), so a door's
// box can turn with it
function boxLinesC(L,C,c){
  for(const[a,b]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]]){const p=C[a],q=C[b];L.push(p[0],p[1],p[2],c[0],c[1],c[2],c[3],q[0],q[1],q[2],c[0],c[1],c[2],c[3]);}
}
// Lines are hidden behind walls like everything else. Only the selection's own (its box,
// its target links, its facing arrow) show through walls, faintly, with X-ray on; they
// go first in the buffer (hotVerts) so the X-ray pass can draw just them.
let LINKS=[], ARROWS=[];
function rebuildLines(){
  const H=[],L=[];
  const sc=hexRGB(TH.sel);
  const selE=selectedEnts();
  for(const X of ENTS){
    if(X.ei===0||!X.box)continue;
    const sel=selE.has(X.ei);
    if(!sel&&(!view.ss||!entVisible(X.ei)))continue;
    if(!sel&&!X.hasGeo&&!X.marker&&X.model<0)continue;
    const b=X.box,dx=X.hasGeo?doorXf(X.ei):null,o=dx?xfP(dx,b.origin):b.origin;
    const c=sel?[sc[0],sc[1],sc[2],1]:[X.col[0],X.col[1],X.col[2],0.85];
    if(dx)boxLinesC(sel?H:L,doorCorners(movObj(X.ei),dx),c);         // a door (or a flying exploder chunk) that has moved: its box moved with it
    else boxLinesC(sel?H:L,boxCorners(b,o),c);
    if(sel){const r=6;H.push(o[0]-r,o[1],o[2],1,1,1,1,o[0]+r,o[1],o[2],1,1,1,1, o[0],o[1]-r,o[2],1,1,1,1,o[0],o[1]+r,o[2],1,1,1,1, o[0],o[1],o[2]-r,1,1,1,1,o[0],o[1],o[2]+r,1,1,1,1);}
  }
  LINKS=[];
  if(view.links){
    for(const X of ENTS){const tg=MAP.ents[X.ei].kvl.target;if(!tg||!X.anchor||!entVisible(X.ei))continue;
      const to=ENTS.tn.get(tg)||[];
      for(const ti of to){const Y=ENTS[ti];if(!Y.anchor||!entVisible(ti))continue;
        const hot=selE.has(X.ei)||selE.has(ti);const c=hot?[sc[0],sc[1],sc[2],1]:[X.col[0],X.col[1],X.col[2],0.75];
        (hot?H:L).push(X.anchor[0],X.anchor[1],X.anchor[2],c[0],c[1],c[2],c[3],Y.anchor[0],Y.anchor[1],Y.anchor[2],c[0],c[1],c[2],c[3]);
        LINKS.push([X.anchor,Y.anchor,c,hot]);}}
    modLinks(H,L,sc,selE);}
  // facing arrows as MOHRadiant draws them (Brush_DrawFacingAngle): white, from the middle
  // of the box out to 2.5 times its half-width, the head half a half-width long and
  // opening up and down. Drawn as 4-pixel bands each frame (drawFacingArrows).
  ARROWS=[];
  if(view.arrows){
    for(const X of ENTS){if(!X.marker||!X.origin||!entShown(X.ei))continue;
      const e=MAP.ents[X.ei];if(e.kvl.angle==null&&e.kvl.angles==null)continue;
      const ax=anglesAxis(entAngles(e.kvl)), f=ax[0], u=ax[2], o=X.origin, b=X.mbox||X.box||{mins:[-8,-8,-8],maxs:[8,8,8]};
      const c=[o[0]+(b.mins[0]+b.maxs[0])/2,o[1]+(b.mins[1]+b.maxs[1])/2,o[2]+(b.mins[2]+b.maxs[2])/2];
      const hw=Math.max(4,(b.maxs[0]-b.mins[0])/2), len=hw*2.5, t=hw*0.5;
      const tip=[c[0]+f[0]*len,c[1]+f[1]*len,c[2]+f[2]*len];
      const h1=[tip[0]-f[0]*t-u[0]*t,tip[1]-f[1]*t-u[1]*t,tip[2]-f[2]*t-u[2]*t], h2=[h1[0]+u[0]*2*t,h1[1]+u[1]*2*t,h1[2]+u[2]*2*t];
      ARROWS.push([c,tip,h1,h2,selE.has(X.ei)]);
    }
    MOD.ents.forEach((m,i)=>{if(!modDrawn(i)||modHasModel(m))return;const kvl=modKvl(m);if(kvl.angle==null&&kvl.angles==null)return;   // a modelled entity gets axes at its origin instead (drawModify)
      const ax=anglesAxis(entAngles(kvl)),f=ax[0],u=ax[2],o=modOrigin(m),b=modBox(m);
      const c=[o[0]+(b.mins[0]+b.maxs[0])/2,o[1]+(b.mins[1]+b.maxs[1])/2,o[2]+(b.mins[2]+b.maxs[2])/2];
      const hw=Math.max(4,(b.maxs[0]-b.mins[0])/2),len=hw*2.5,t=hw*0.5,tip=[c[0]+f[0]*len,c[1]+f[1]*len,c[2]+f[2]*len];
      const h1=[tip[0]-f[0]*t-u[0]*t,tip[1]-f[1]*t-u[1]*t,tip[2]-f[2]*t-u[2]*t],h2=[h1[0]+u[0]*2*t,h1[1]+u[1]*2*t,h1[2]+u[2]*2*t];
      ARROWS.push([c,tip,h1,h2,i===MOD.sel]);});
    ARROWS.sort((a,b)=>(b[4]?1:0)-(a[4]?1:0));
  }
  // the selection's links first, so the arrowheads can be drawn in the same two passes
  LINKS.sort((a,b)=>(b[3]?1:0)-(a[3]?1:0));
  const all=H.concat(L);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.line);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(all.length?all:new Array(7).fill(0)),gl.DYNAMIC_DRAW);
  lineVerts=all.length/7;hotVerts=H.length/7;lineDirty=false;
}
// The arrowhead on each target link, 70% of the way along: a small triangle facing the
// camera, about 7 pixels across wherever it is, hidden behind walls like the line.
function drawLinkHeads(){
  if(!view.links||!LINKS.length)return;
  const a=camAxes(), e=cam.pos, k=2*Math.tan(fovX*Math.PI/360)/W, C=Math.cos(2.5), S=Math.sin(2.5), P=[];
  let hot=0;
  for(const[A,Bq,c,h]of LINKS){
    const p=[A[0]+(Bq[0]-A[0])*0.7,A[1]+(Bq[1]-A[1])*0.7,A[2]+(Bq[2]-A[2])*0.7];
    const rel=[p[0]-e[0],p[1]-e[1],p[2]-e[2]], z=vdot(rel,a.f);if(z<NEAR)continue;
    const d=vnorm([Bq[0]-A[0],Bq[1]-A[1],Bq[2]-A[2]]), vd=vnorm(rel);if(!d||!vd)continue;
    const t=vdot(d,vd), u=vnorm([d[0]-vd[0]*t,d[1]-vd[1]*t,d[2]-vd[2]*t]);if(!u)continue;   // pointing at the camera
    const v=vnorm(vcross(vd,u));if(!v)continue;
    const r=7*z*k, al=Math.max(c[3],0.9);
    for(const[x,y]of[[1,0],[C,S],[C,-S]])
      P.push(p[0]+(u[0]*x+v[0]*y)*r,p[1]+(u[1]*x+v[1]*y)*r,p[2]+(u[2]*x+v[2]*y)*r,c[0],c[1],c[2],al);
    if(h)hot+=3;
  }
  if(!P.length)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,B.head);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(P),gl.STREAM_DRAW);
  gl.bindVertexArray(B.vHead);gl.disable(gl.CULL_FACE);
  if(view.xray&&hot){gl.depthFunc(gl.GREATER);gl.uniform1f(PL.u.uAlpha,0.35);gl.drawArrays(gl.TRIANGLES,0,hot);}
  gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,1);gl.drawArrays(gl.TRIANGLES,0,P.length/7);
}
// The facing arrows' three strokes, each a camera-facing band 4 pixels wide wherever it is
// (MOHRadiant draws them with glLineWidth 4), cut at the near plane and hidden behind
// walls like the lines; the selection's own go first, for the X-ray pass.
function drawFacingArrows(){
  if(!view.arrows||!ARROWS.length)return;
  const a=camAxes(), e=cam.pos, k=2*Math.tan(fovX*Math.PI/360)/W, P=[];
  const depth=p=>(p[0]-e[0])*a.f[0]+(p[1]-e[1])*a.f[1]+(p[2]-e[2])*a.f[2];
  const band=(A,B)=>{
    let za=depth(A), zb=depth(B);
    if(za<NEAR&&zb<NEAR)return 0;
    if(za<NEAR){const t=(NEAR-za)/(zb-za);A=[A[0]+(B[0]-A[0])*t,A[1]+(B[1]-A[1])*t,A[2]+(B[2]-A[2])*t];za=NEAR;}
    else if(zb<NEAR){const t=(NEAR-zb)/(za-zb);B=[B[0]+(A[0]-B[0])*t,B[1]+(A[1]-B[1])*t,B[2]+(A[2]-B[2])*t];zb=NEAR;}
    const m=[(A[0]+B[0])/2-e[0],(A[1]+B[1])/2-e[1],(A[2]+B[2])/2-e[2]];
    const s=vnorm(vcross([B[0]-A[0],B[1]-A[1],B[2]-A[2]],m));if(!s)return 0;
    const wa=2*za*k, wb=2*zb*k;
    const a0=[A[0]+s[0]*wa,A[1]+s[1]*wa,A[2]+s[2]*wa], a1=[A[0]-s[0]*wa,A[1]-s[1]*wa,A[2]-s[2]*wa];
    const b0=[B[0]+s[0]*wb,B[1]+s[1]*wb,B[2]+s[2]*wb], b1=[B[0]-s[0]*wb,B[1]-s[1]*wb,B[2]-s[2]*wb];
    for(const v of[a0,a1,b0,a1,b1,b0])P.push(v[0],v[1],v[2],1,1,1,1);
    return 6;
  };
  let hot=0;
  for(const[c,tip,h1,h2,h]of ARROWS){const n=band(c,tip)+band(tip,h1)+band(tip,h2);if(h)hot+=n;}
  if(!P.length)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,B.arw);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(P),gl.STREAM_DRAW);
  gl.bindVertexArray(B.vArw);gl.disable(gl.CULL_FACE);
  if(view.xray&&hot){gl.depthFunc(gl.GREATER);gl.uniform1f(PL.u.uAlpha,0.35);gl.drawArrays(gl.TRIANGLES,0,hot);}
  gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,1);gl.drawArrays(gl.TRIANGLES,0,P.length/7);
}
function drawLines(vp){
  if(lineDirty)rebuildLines();
  gl.useProgram(PL);gl.uniformMatrix4fv(PL.u.uVP,false,vp);gl.uniform1f(PL.u.uAlpha,1);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.DEPTH_TEST);gl.depthMask(false);
  if(view.wire&&wireCount){gl.bindVertexArray(B.vEdge);gl.disableVertexAttribArray(7);
    const c=document.documentElement.classList.contains('light')?[0,0,0,0.35]:[1,1,1,0.28];gl.vertexAttrib4f(7,c[0],c[1],c[2],c[3]);
    gl.drawElements(gl.LINES,wireCount,gl.UNSIGNED_INT,0);}
  if(lineVerts){gl.bindVertexArray(B.vLine);
    if(view.xray&&hotVerts){gl.depthFunc(gl.GREATER);gl.uniform1f(PL.u.uAlpha,0.3);gl.drawArrays(gl.LINES,0,hotVerts);}
    gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,1);gl.drawArrays(gl.LINES,0,lineVerts);}
  drawLinkHeads();
  drawFacingArrows();
  gl.bindVertexArray(null);gl.depthMask(true);gl.disable(gl.BLEND);gl.depthFunc(gl.LEQUAL);
}

// ---- 2D overlay: labels, the Radiant fly crosshair -------------------------------------
let _d2d=true;                // the overlay has something on it (cleared only then)
function draw2D(){
  const any=view.labels||radFly||(view.leak&&leakHas())||GRID.on||!!(PA_ISS&&PA_ISS.n&&MOD.ents.length)||!!(CVARS.ai_showroutes&&ROUTES&&ROUTES.tags&&ROUTES.tags.size);
  if(!any&&!_d2d)return;
  ctx.clearRect(0,0,W,H);_d2d=!!any;
  const selE=selectedEnts();
  if(view.labels){
    // Nearest first, never overlapping: named entities out to 2048 units, unnamed ones
    // close by only (700; brush entities too: doors, ladders...), lights and static props
    // only when named (there are hundreds).
    // Behind a wall, less far: 512 named, 350 unnamed, a label past that showing only when
    // the camera can see its spot (lblSeen: a sight line through the world's opaque
    // brushes). Each fades out over the last 40% of its own range, to nothing at its end.
    // Selected ones always show, fully. With X-ray off, no label shows through a wall at
    // all: each needs a sight line to its spot, at any distance, selected ones too.
    const cand=[];lblOccluders();
    for(const X of ENTS){if(X.ei===0||!X.anchor||!entVisible(X.ei))continue;
      const sel=selE.has(X.ei), e=MAP.ents[X.ei], tn=e.kvl.targetname;
      if(!sel&&!tn&&(X.marker===2||(X.cat&C_STATIC)))continue;
      if(!sel&&X.hasGeo&&isWorldlike(X.ei))continue;          // func_group, detail: part of the world
      const d=Math.hypot(X.anchor[0]-cam.pos[0],X.anchor[1]-cam.pos[1],X.anchor[2]-cam.pos[2]);
      if(!sel&&d>(tn?2048:700))continue;
      cand.push([sel?-1:d,X]);}
    // Modify's entities, labelled the same way with a badge in front: NEW for an added one,
    // EDIT for one of the map's that Modify has changed (Modify draws it instead of the
    // map's marker, so the map's label isn't drawn)
    MOD.ents.forEach((m,i)=>{if(!modDrawn(i))return;
      const o=modOrigin(m),b=modBox(m),k=simKvl(m),tn=k.targetname,sel=modIsSel(i);
      const d=Math.hypot(o[0]-cam.pos[0],o[1]-cam.pos[1],o[2]-cam.pos[2]);
      if(!sel&&d>(tn?2048:700))return;
      cand.push([sel?-1:d,{mod:m,anchor:o,top:[o[0],o[1],o[2]+b.maxs[2]+6],e:{cls:modCls(m),kvl:k},
        badge:modIsMap(m)?(m.del?'DEL':modEdited(m)?'EDIT':''):'NEW'}]);});
    cand.sort((a,b)=>a[0]-b[0]);
    ctx.font='11px ui-monospace,Menlo,Consolas,monospace';ctx.textBaseline='middle';
    const taken=[];let shown=0;
    for(const[d,X]of cand){if(shown>=120&&d>=0)break;
      // a brush entity's in the middle of its box (a door's origin is its hinge, often in
      // the wall), where it is now if it has moved
      let top;
      if(X.mod)top=X.top;
      else if(X.hasGeo&&X.box){const b=X.box,dx=doorXf(X.ei),c=[b.origin[0]+(b.mins[0]+b.maxs[0])/2,b.origin[1]+(b.mins[1]+b.maxs[1])/2,b.origin[2]+(b.mins[2]+b.maxs[2])/2];
        top=dx?xfP(dx,c):c;}
      else{const mb=X.mbox||X.box;top=mb?[X.anchor[0],X.anchor[1],X.anchor[2]+(X.marker?mb.maxs[2]+6:0)]:X.anchor;}
      const sp=project(top);if(!sp||sp[0]<-50||sp[0]>W+50||sp[1]<-20||sp[1]>H+20)continue;
      const e=X.mod?X.e:MAP.ents[X.ei], tn=e.kvl.targetname;
      let lim=tn?2048:700;const wall=tn?512:350;
      if(!view.xray){if(!lblSeen(X.mod?'m'+X.mod.id:X.ei,top))continue;}
      else if(d>=0&&d>wall*0.6&&!lblSeen(X.mod?'m'+X.mod.id:X.ei,top))lim=wall;
      const al=d<0?1:Math.min(1,(lim-d)/(lim*0.4));
      if(al<0.04)continue;
      const txt=(e.kvl.classname||e.cls||'?')+nodeFlagTag(e)+(tn?'  $'+tn:'');
      // the badge: small bold capitals on a filled tab, inside the label's left end
      const bg=X.badge||'';let bw=0;
      if(bg){ctx.font='bold 9px ui-monospace,Menlo,Consolas,monospace';bw=ctx.measureText(bg).width+8;ctx.font='11px ui-monospace,Menlo,Consolas,monospace';}
      const tw=ctx.measureText(txt).width, full=tw+(bw?bw+4:0), x0=sp[0]-full/2, r=[x0-4,sp[1]-16,full+8,14];
      if(d>=0&&taken.some(q=>r[0]<q[0]+q[2]&&q[0]<r[0]+r[2]&&r[1]<q[1]+q[3]&&q[1]<r[1]+r[3]))continue;
      taken.push(r);
      ctx.globalAlpha=al;ctx.fillStyle='rgba('+TH.labelbg+',.8)';ctx.fillRect(r[0],r[1],r[2],r[3]);
      if(bw){ctx.fillStyle=bg==='NEW'?'#ffb020':'#6ea8ff';ctx.fillRect(x0-2,sp[1]-15,bw,12);
        ctx.font='bold 9px ui-monospace,Menlo,Consolas,monospace';ctx.fillStyle='#14181d';ctx.fillText(bg,x0+2,sp[1]-9);
        ctx.font='11px ui-monospace,Menlo,Consolas,monospace';}
      ctx.fillStyle=d<0?TH.sel:(tn?TH.accent:TH.txt);ctx.fillText(txt,x0+(bw?bw+4:0),sp[1]-9);
      shown++;}
    ctx.globalAlpha=1;
  }
  drawLeak2D();
  drawGrid2D();
  drawPathIssues2D();
  if(radFly){ctx.strokeStyle=TH.accent;ctx.globalAlpha=0.8;ctx.lineWidth=1;ctx.beginPath();
    ctx.moveTo(W/2-10,H/2);ctx.lineTo(W/2+10,H/2);ctx.moveTo(W/2,H/2-10);ctx.lineTo(W/2,H/2+10);ctx.stroke();
    ctx.beginPath();ctx.moveTo(W/2,H/2);ctx.lineTo(radFly.x,radFly.y);ctx.stroke();ctx.globalAlpha=1;}
}

// ============================================================================
//  The game's own view: r_showtris (what the renderer draws from the camera)
// ============================================================================
// tr_world.c: the camera's leaf (R_PointInLeaf) names its cluster, and R_MarkLeaves keeps
// the leafs whose cluster is in that cluster's row of the vis lump and whose area is
// joined to the camera's. Doors cut a map into areas: the areas are flooded through the
// open area portals (cm_test.c), a level starts with every door shut but the ones that
// start open, Open door opens and shuts them as in game (see Doors), and cm_noAreas 1
// joins them all. From a leaf with no cluster (outside the map) every leaf is kept.
// R_RecursiveWorldNode walks the tree, dropping the boxes past the farplane, and
// R_AddWorldSurface drops the planar faces facing away from the camera (with 8 units of
// slack) and the triangle soups and curved patches past the farplane; a patch keeps only
// the rows and columns its distance allows (RB_SurfaceGrid with r_lodCurveError 250).
// Brush entities and models are sent to the client only when a cluster their box touches
// is in the PVS and their area is joined to the camera's (sv_snapshot.c); static props
// are listed by the leafs. A door that has moved is drawn where it is now. r_showtris
// then outlines every triangle that was drawn (tr_shade.c DrawTris): 1 hidden behind
// walls, 2 through them, with an axis cross at the origin of each model drawn (red up,
// green along y, blue a diagonal: the engine's own slip), 3 the crosses alone. Terrain is
// outlined at full detail (the game thins it out with distance) and models at their full
// detail too.
let GV=null;
const DOOR_CLASSES={func_door:1,func_rotatingdoor:1,script_door:1};
function gvInit(){
  const V=D.vis;if(!V||!V.nl)return;
  const G={np:D.f32(V.np),nc:D.i32(V.nc),nb:D.i32(V.nb),lf:D.i32(V.lf),ls:D.i32(V.ls),lt:D.i32(V.lt),lm:D.i32(V.lm),
    pvs:V.pvs!=null?D.bytes(V.pvs):null,ncl:V.ncl|0,cb:V.cb|0,si:D.i32(V.si),sf:D.f32(V.sf),v:D.f32(V.v),l:D.u32(V.l),
    ge:D.f32(V.ge),nn:V.nn|0,nl:V.nl|0,ns:V.ns|0,sk:V.sk!=null?D.u32(V.sk):new Uint32Array(0),
    vn:V.vn!=null?D.nrm(V.vn):null,              // r_shownormals: each point's normal
    sun:V.sun!=null?D.bytes(V.sun):null};        // the leafs that see the sun (sunLeafOK)
  let na=0;for(let l=0;l<G.nl;l++){const a=G.lf[l*14+1];if(a+1>na)na=a+1;}
  G.na=na;
  gvFar(G);
  // The lines are kept as their two ends (each vertex knows the other end, so a line that
  // runs behind the camera can be cut at the near plane: see VS_GVL). The surfaces' lines
  // come first, in the .bsp's order (vertex m of the list is the m-th line end of G.l),
  // then the terrain's, each block's edges once, from the page's own terrain.
  const blk=new Map();SC.prims.forEach((p,pi)=>{if(p.ent===0&&p.kind===2)blk.set(p.bn,pi);});
  G.terPrim=(V.to||[]).map(bn=>blk.has(bn)?blk.get(bn):-1);
  const TL=[];G.terRange=G.terPrim.map(pi=>{
    if(pi<0)return null;const p=SC.prims[pi],seen=new Set(),start=G.l.length+TL.length;
    for(let fc=p.f0;fc<p.f1;fc++)for(let k=SC.faceE0[fc],ke=k+SC.faceEN[fc];k+1<ke;k+=2){
      let a=SC.edge[k],b=SC.edge[k+1];if(a>b){const x=a;a=b;b=x;}const key=a*SC.nv+b;
      if(!seen.has(key)){seen.add(key);TL.push(a,b);}}
    return [start,G.l.length+TL.length-start];});
  G.terLines=new Uint32Array(TL);
  G.idx=new Uint32Array(Math.max(2,G.l.length+TL.length));
  // r_shownormals: the ends of the normal lines to draw, two per point of G.v
  G.nidx=G.vn?new Uint32Array(Math.max(2,G.v.length/3*2)):null;G.nNIdx=0;G.nstats='';
  // a patch's lines are made each time, as many as its finest level can have
  let gm=0;for(let s=0;s<G.ns;s++)if(G.si[s*8]===3){const w=G.si[s*8+4],h=G.si[s*8+5];gm+=(w-1)*h+w*(h-1)+(w-1)*(h-1);}
  G.grid=new Float32Array(Math.max(12,gm*12));
  G.stS=new Int32Array(G.ns).fill(-1);G.stT=new Int32Array(Math.max(1,(V.to||[]).length)).fill(-1);G.stM=new Int32Array(Math.max(1,G.lm.length)).fill(-1);
  G.frame=0;
  // brush entities: their own surfaces
  G.bm=new Map();for(const r of V.bm||[]){let a=G.bm.get(r[0]);if(!a){a=[];G.bm.set(r[0],a);}a.push(r[1],r[2]);}
  // every entity the game sends: its clusters and areas from its box grown by a unit
  // (SV_LinkEntity). A door's two areas are the ones its area portal joins while it is
  // open; the doors keep G.portals, the pairs open now (doorPortals).
  G.ent=new Map();G.portals=[];G.doorArea=new Map();
  const fs=D.bsp&&D.bsp.firstStatic!=null?D.bsp.firstStatic:MAP.ents.length;
  for(const X of ENTS){
    if(X.ei===0||X.ei>=fs||!X.box)continue;
    const door=DOOR_CLASSES[MAP.ents[X.ei].cls];
    if(!G.bm.has(X.ei)&&X.model<0&&!door)continue;
    const b=X.box,o=b.origin;
    const E=gvLink(G,X.ei,[o[0]+b.wmins[0],o[1]+b.wmins[1],o[2]+b.wmins[2]],[o[0]+b.wmaxs[0],o[1]+b.wmaxs[1],o[2]+b.wmaxs[2]]);
    if(door)G.doorArea.set(X.ei,[E.a1,E.a2]);
  }
  G.key='';G.skey='';G.marked=false;G.leafVis=new Uint8Array(G.nl);G.nodeVis=new Uint8Array(Math.max(1,G.nn));G.conn=null;G.camArea=-1;G.camCluster=-1;
  G.sig='';G.nIdx=0;G.nGrid=0;G.nX=0;G.stats='';
  GV=G;
}
// The farplane the game culls with: the map's (worldspawn "farplane" and "farplane_cull":
// nodes are dropped past it with farplane_cull 1, the default, boxes and spheres with any
// but 0; terrain patches 768 units past it), or r_farplane's in its place with
// r_farplane_nocull (1 none, 0 standard, -1 as for a portal sky: R_SetupFrustum).
function gvFar(G){
  const wk=MAP.ents[0]?MAP.ents[0].kvl:{};
  let far=parseFloat(wk.farplane)||0,fc=wk.farplane_cull!=null?parseInt(wk.farplane_cull,10)||0:1;
  if(farOverride()){far=CVARS.r_farplane;const n=CVARS.r_farplane_nocull;fc=n>0?0:n===0?1:2;}
  G.far=far;G.farNodes=far>0&&fc===1;G.farBoxes=far>0&&fc!==0;
}
// The leafs a box touches (CM_BoxLeafnums), with BoxOnPlaneSide's quick test for the
// axial planes.
function gvBoxLeafs(G,mn,mx,out){
  if(!G.nn){out.push(0);return;}
  const st=[0];
  while(st.length){
    let n=st.pop();
    while(n>=0){
      const o=n*4,nx=G.np[o],ny=G.np[o+1],nz=G.np[o+2],d=G.np[o+3];let s;
      if(nx===1)s=d<=mn[0]?1:(d>=mx[0]?2:3);
      else if(ny===1)s=d<=mn[1]?1:(d>=mx[1]?2:3);
      else if(nz===1)s=d<=mn[2]?1:(d>=mx[2]?2:3);
      else{const d1=(nx>0?mx[0]:mn[0])*nx+(ny>0?mx[1]:mn[1])*ny+(nz>0?mx[2]:mn[2])*nz,
                 d2=(nx>0?mn[0]:mx[0])*nx+(ny>0?mn[1]:mx[1])*ny+(nz>0?mn[2]:mx[2])*nz;
        s=0;if(d1>=d)s=1;if(d2<d)s|=2;}
      if(s===1)n=G.nc[n*2];else if(s===2)n=G.nc[n*2+1];else{st.push(G.nc[n*2]);n=G.nc[n*2+1];}
    }
    out.push(-(n+1));
  }
}
// Link an entity with the box mn..mx (SV_LinkEntity): the clusters and the (at most two)
// areas of the leafs the box touches, grown by a unit on every side. A door that moves is
// linked again as it goes.
function gvLink(G,ei,mn,mx){
  const leafs=[];gvBoxLeafs(G,[mn[0]-1,mn[1]-1,mn[2]-1],[mx[0]+1,mx[1]+1,mx[2]+1],leafs);
  const cl=[];let a1=-1,a2=-1;
  for(const l of leafs){const c=G.lf[l*14],a=G.lf[l*14+1];
    if(a>=0){if(a1>=0&&a1!==a)a2=a;else a1=a;}
    if(c>=0&&!cl.includes(c))cl.push(c);}
  const E={cl:cl,a1:a1,a2:a2,mn:mn.slice(),mx:mx.slice()};
  G.ent.set(ei,E);return E;
}
function gvPointLeaf(G,p){
  if(!G.nn)return 0;
  let n=0;
  while(n>=0){const o=n*4;n=(p[0]*G.np[o]+p[1]*G.np[o+1]+p[2]*G.np[o+2]-G.np[o+3]>0)?G.nc[n*2]:G.nc[n*2+1];}
  return -(n+1);
}
// The areas joined to the camera's (CM_FloodAreaConnections through the open portals),
// or null when every area counts as joined.
function gvAreas(G,area){
  if(CVARS.cm_noAreas||area<0||G.na<2)return null;
  const conn=new Uint8Array(G.na);conn[area]=1;
  let grew=true;
  while(grew){grew=false;for(const[a,b]of G.portals){if(conn[a]&&!conn[b]){conn[b]=1;grew=true;}else if(conn[b]&&!conn[a]){conn[a]=1;grew=true;}}}
  return conn;
}
// The server's view of the camera (which entities it sends: gvSent) is always where the
// camera is. R_MarkLeaves: the leafs the renderer keeps for the camera's cluster and area,
// and every node above one; r_lockpvs keeps the last ones marked (it returns at once),
// r_novis marks every leaf.
function gvMark(G,leaf){
  const cl=G.lf[leaf*14],area=G.lf[leaf*14+1];
  const skey=cl+':'+area+':'+(CVARS.cm_noAreas?1:0);
  if(skey!==G.skey){G.skey=skey;G.camArea=area;G.camCluster=cl;G.conn=cl<0?null:gvAreas(G,area);}
  if(CVARS.r_lockpvs&&G.marked)return;
  const key=CVARS.r_novis?'novis':skey;
  if(key===G.key)return;
  G.key=key;G.marked=true;G.markCl=cl;G.markArea=area;
  const lv=G.leafVis;lv.fill(0);
  if(cl<0||CVARS.r_novis)lv.fill(1);       // no PVS for a leaf outside the map (or r_novis): everything
  else{
    const row=(G.pvs&&cl<G.ncl)?cl*G.cb:-1;
    for(let l=0;l<G.nl;l++){
      const c=G.lf[l*14];if(c<0)continue;
      if(row>=0&&!(G.pvs[row+(c>>3)]&(1<<(c&7))))continue;
      const a=G.lf[l*14+1];if(G.conn&&(a<0||!G.conn[a]))continue;
      lv[l]=1;}
  }
  // a node is walked if any leaf under it is kept
  const nv=G.nodeVis;nv.fill(0);
  if(G.nn){
    const st=[[0,0]];
    while(st.length){
      const top=st[st.length-1],n=top[0];
      if(top[1]<2){const c=G.nc[n*2+top[1]];top[1]++;if(c>=0)st.push([c,0]);continue;}
      st.pop();
      let v=0;for(let k=0;k<2;k++){const c=G.nc[n*2+k];if(c>=0?nv[c]:lv[-(c+1)])v=1;}
      nv[n]=v;
    }
  }
}
// Does the server send this entity to the camera (sv_snapshot.c)? Its area joined to the
// camera's (CM_AreasConnected: never from or to area -1), and a cluster its box touches
// in the camera's PVS (CM_ClusterPVS gives the first row for a cluster it has no row for).
function gvSent(G,ei){
  const E=G.ent.get(ei);if(!E||!E.cl.length)return false;
  if(!CVARS.cm_noAreas){
    if(G.camArea<0)return false;
    if(G.conn){if(!((E.a1>=0&&G.conn[E.a1])||(E.a2>=0&&G.conn[E.a2])))return false;}
    else if(E.a1<0&&E.a2<0)return false;
  }
  if(!G.pvs)return true;
  const row=(G.camCluster>=0&&G.camCluster<G.ncl)?G.camCluster*G.cb:0;
  for(const c of E.cl)if(G.pvs[row+(c>>3)]&(1<<(c&7)))return true;
  return false;
}
// past the farplane: the box's nearest corner along the view is further than the farplane
function gvBeyond(f,fe,far,x0,y0,z0,x1,y1,z1){
  return (f[0]>0?x0:x1)*f[0]+(f[1]>0?y0:y1)*f[1]+(f[2]>0?z0:z1)*f[2]-fe>far;
}
// Everything the game draws from the camera: the line ends to draw out of the fixed list
// (G.idx), the patches' lines as they are now (G.grid), each model's visible instances and
// the axis crosses. Sent to the graphics card only when something changed.
function gvUpdate(){
  const G=GV;
  if(G.upd===FRAMES&&!G.dirty)return;            // once a frame
  G.upd=FRAMES;gvFar(G);
  const e=cam.pos,f=camAxes().f,fe=f[0]*e[0]+f[1]*e[1]+f[2]*e[2],far=G.far;
  const nodeFar=G.farNodes,boxFar=G.farBoxes;
  gvMark(G,gvPointLeaf(G,e));
  const fr=++G.frame,surfs=[],ters=[],stats=[];
  const lf=G.lf,nb=G.nb;
  const leaf=l=>{
    const o=l*14;
    for(let k=lf[o+8],ke=k+lf[o+9];k<ke;k++){const s=G.ls[k];if(s>=0&&s<G.ns&&G.stS[s]!==fr){G.stS[s]=fr;surfs.push(s);}}
    for(let k=lf[o+10],ke=k+lf[o+11];k<ke;k++){const t=G.lt[k];if(t>=0&&t<G.stT.length&&G.stT[t]!==fr){G.stT[t]=fr;ters.push(t);}}
    for(let k=lf[o+12],ke=k+lf[o+13];k<ke;k++){const m=G.lm[k];if(m>=0&&m<G.stM.length&&G.stM[m]!==fr){G.stM[m]=fr;stats.push(m);}}
  };
  if(!G.nn){if(G.leafVis[0])leaf(0);}
  else{
    const st=[0];
    while(st.length){
      let n=st.pop();
      for(;;){
        if(n>=0){
          if(!G.nodeVis[n])break;
          const b=n*6;if(nodeFar&&gvBeyond(f,fe,far,nb[b],nb[b+1],nb[b+2],nb[b+3],nb[b+4],nb[b+5]))break;
          st.push(G.nc[n*2]);n=G.nc[n*2+1];continue;}
        const l=-(n+1);
        if(G.leafVis[l]){const o=l*14+2;
          if(!(nodeFar&&gvBeyond(f,fe,far,lf[o],lf[o+1],lf[o+2],lf[o+3],lf[o+4],lf[o+5])))leaf(l);}
        break;
      }
    }
  }
  // the surfaces: faces facing away dropped (R_CullSurface), soups and patches past the farplane
  let n=0,ng=0,sig=0;const out=G.idx,gr=G.grid,si=G.si,sf=G.sf,P=G.v;
  const cnt=[0,0,0,0];
  // r_shownormals: the same points' normal lines (DrawNormals runs on every batch drawn)
  const nout=G.nidx;let nn=0,nnF=0,nnP=0,nnM=0;
  const gline=(i,j)=>{gr.set([P[i*3],P[i*3+1],P[i*3+2],P[j*3],P[j*3+1],P[j*3+2],P[j*3],P[j*3+1],P[j*3+2],P[i*3],P[i*3+1],P[i*3+2]],ng);ng+=12;};
  const sky=[];
  const add=s=>{
    const o=s*8,k=si[o],q=s*10;
    // a sky polygon isn't outlined (the sky box is drawn there), but r_showsky needs those
    // drawn, turned away ones dropped as for a face
    if(k===4){const c=si[o+1];
      if(c!==2){const d=e[0]*sf[q]+e[1]*sf[q+1]+e[2]*sf[q+2];if(c===0?d<sf[q+3]-8:d>sf[q+3]+8)return false;}
      sky.push(s);return false;}
    if(k===1){
      const c=si[o+1];
      if(c!==2){const d=e[0]*sf[q]+e[1]*sf[q+1]+e[2]*sf[q+2];if(c===0?d<sf[q+3]-8:d>sf[q+3]+8)return false;}
    }else if(k===2||k===3){
      if(boxFar&&gvBeyond(f,fe,far,sf[q+4],sf[q+5],sf[q+6],sf[q+7],sf[q+8],sf[q+9]))return false;
    }else return false;
    if(k===3){
      // RB_SurfaceGrid: the rows and columns whose error the distance allows
      const v0=si[o+3],w=si[o+4],h=si[o+5],eo=si[o+6];
      let d=Math.abs((sf[q]-e[0])*f[0]+(sf[q+1]-e[1])*f[1]+(sf[q+2]-e[2])*f[2])-sf[q+3];if(d<1)d=1;
      const lod=250/d,wt=[0],ht=[0];
      for(let i=1;i<w-1;i++)if(G.ge[eo+i]<=lod)wt.push(i);wt.push(w-1);
      for(let i=1;i<h-1;i++)if(G.ge[eo+w+i]<=lod)ht.push(i);ht.push(h-1);
      // each quad as RB_SurfaceGrid splits it: its sides and the diagonal from its lower
      // left to its upper right
      for(let r=0;r<ht.length;r++)for(let c=0;c<wt.length;c++){
        const p=v0+ht[r]*w+wt[c];
        if(c+1<wt.length)gline(p,v0+ht[r]*w+wt[c+1]);
        if(r+1<ht.length){gline(p,v0+ht[r+1]*w+wt[c]);if(c+1<wt.length)gline(v0+ht[r+1]*w+wt[c],v0+ht[r]*w+wt[c+1]);}}
      sig=(Math.imul(sig,31)+s*7+wt.length*131+ht.length)|0;
      // the grid points RB_SurfaceGrid emits: those of the rows and columns kept
      if(nout){for(const r of ht)for(const c of wt){const v=v0+r*w+c;nout[nn++]=2*v;nout[nn++]=2*v+1;}nnP+=ht.length*wt.length;}
    }else{const a=si[o+3],c=si[o+4];for(let m=a;m<a+c;m++)out[n++]=m;sig=(Math.imul(sig,31)+s)|0;
      // every point of the face or soup (RB_SurfaceFace, RB_SurfaceTriangles)
      if(nout){const vb=si[o+5],vc=si[o+6];for(let v=vb;v<vb+vc;v++){nout[nn++]=2*v;nout[nn++]=2*v+1;}nnF+=vc;}}
    cnt[k]++;
    return true;
  };
  let world=false;
  for(const s of surfs)if(add(s))world=true;
  G.skyNow=sky;
  // terrain patches from the kept leafs, but not 768 units past the farplane (R_MarkTerrainPatch)
  let nter=0;
  for(const t of ters){const R=G.terRange[t];if(!R)continue;const p=SC.prims[G.terPrim[t]];
    if(far>0&&((p.mins[0]+p.maxs[0])/2-e[0])*f[0]+((p.mins[1]+p.maxs[1])/2-e[1])*f[1]+((p.mins[2]+p.maxs[2])/2-e[2])*f[2]>far+768)continue;
    for(let m=R[0];m<R[0]+R[1];m++)out[n++]=m;
    world=true;nter++;sig=(Math.imul(sig,31)+t*3+1)|0;}
  // crosses: the world's (at the origin), then each brush entity and model drawn
  const X=[];
  const cross=(o,ax,len)=>{
    const Q=(x,y,z)=>[o[0]+(ax[0][0]*x+ax[1][0]*y+ax[2][0]*z)*len,o[1]+(ax[0][1]*x+ax[1][1]*y+ax[2][1]*z)*len,o[2]+(ax[0][2]*x+ax[1][2]*y+ax[2][2]*z)*len];
    for(const[a,b,c]of[[Q(0,0,-5),Q(0,0,5),[1,0,0]],[Q(0,-5,0),Q(0,5,0),[0,1,0]],[Q(-5,0,0),Q(5,5,0),[0,0,1]]])
      X.push(a[0],a[1],a[2],b[0],b[1],b[2],c[0],c[1],c[2],1,b[0],b[1],b[2],a[0],a[1],a[2],c[0],c[1],c[2],1);};
  const I3=[[1,0,0],[0,1,0],[0,0,1]];
  if(world)cross([0,0,0],I3,1);
  let nbm=0,nmod=0;
  for(const[ei,ranges]of G.bm){
    if(!gvSent(G,ei))continue;
    const E=G.ent.get(ei);if(boxFar&&E&&gvBeyond(f,fe,far,E.mn[0],E.mn[1],E.mn[2],E.mx[0],E.mx[1],E.mx[2]))continue;
    let any=false;
    for(let r=0;r<ranges.length;r+=2)for(let s=ranges[r];s<ranges[r]+ranges[r+1]&&s<G.ns;s++)if(add(s))any=true;
    // a door that has moved: its origin where it is now, its axes turned with it
    if(any){const dx=doorXf(ei),o=ENTS[ei].origin||[0,0,0];
      cross(dx?xfP(dx,o):o,dx&&dx.ang?anglesAxis(dx.ang):dx&&dx.yaw?anglesAxis([0,dx.yaw,0]):I3,1);nbm++;sig=(Math.imul(sig,31)+ei*5+2)|0;}
  }
  // models: entities the server sends, static props their leafs list
  const fs=D.bsp&&D.bsp.firstStatic!=null?D.bsp.firstStatic:MAP.ents.length;
  const vis=new Set();
  for(const m of stats){const ei=fs+m;if(ei<ENTS.length&&ENTS[ei].model>=0)vis.add(ei);}
  for(const ei of G.ent.keys())if(ENTS[ei].model>=0&&gvSent(G,ei))vis.add(ei);
  for(const R of MODELS){
    const a=[],an=[];
    for(const ei of R.inst){if(!vis.has(ei))continue;
      const E=ENTS[ei],b=E.box,o=E.origin;
      if(boxFar&&b&&gvBeyond(f,fe,far,o[0]+b.wmins[0],o[1]+b.wmins[1],o[2]+b.wmins[2],o[0]+b.wmaxs[0],o[1]+b.wmaxs[1],o[2]+b.wmaxs[2]))continue;
      const rows=instRows(E);for(const v of rows)a.push(v);nmod++;sig=(Math.imul(sig,31)+ei*11+3)|0;
      // a static prop's cross takes its .tik scale and its own (R_RotateForStaticModel);
      // an entity's axes are unit length
      const kv=MAP.ents[ei].kvl,ax=anglesAxis(entAngles(kv)),ks=parseFloat(kv.scale)||1;
      cross(o,ax,ei>=fs?ks*(R.M.sc||1):1);
      // r_shownormals: a static prop's lines are 2 of its own units (its scale is in the
      // matrix), an entity's 2 world units (RB_SkelMesh scales the points, not the normals)
      if(R.nVao){for(const v of rows)an.push(v);an.push(ei>=fs?2*(R.M.sc||1):2/ks);nnM+=R.nVerts/2;}
    }
    R.gvRows=a;R.gvNRows=an;
  }
  const pl=(v,w,ws)=>v+' '+(v===1?w:(ws||w+'s'));
  G.stats=[pl(cnt[1],'face'),cnt[2]?pl(cnt[2],'triangle soup'):'',cnt[3]?pl(cnt[3],'patch','patches'):'',
    nter?pl(nter,'terrain block'):'',nbm?pl(nbm,'brush entity','brush entities'):'',pl(nmod,'model')].filter(Boolean).join(' · ');
  if(nout)G.nstats=pl(nnF+nnP+nnM,'line')+': '+[pl(nnF,'face point'),nnP?pl(nnP,'curve point'):'',nnM?pl(nnM,'model vertex','model vertices'):'']
    .filter(Boolean).join(' · ')+(nter?'; none on the terrain (the renderer makes it no normals)':'');
  const key=sig+':'+n+':'+ng+':'+X.length;
  G.nX=X.length/10;
  if(key===G.sig&&!G.dirty)return;
  G.sig=key;G.dirty=false;G.nIdx=n;G.nGrid=ng/6;
  gl.bindVertexArray(null);                      // the element buffers below are bound loose
  if(B.gvNIdx){G.nNIdx=nn;
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.gvNIdx);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,nout.subarray(0,Math.max(2,nn)),gl.DYNAMIC_DRAW);
    for(const R of MODELS){if(!R.nVao)continue;
      gl.bindBuffer(gl.ARRAY_BUFFER,R.nInst);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(R.gvNRows.length?R.gvNRows:new Array(13).fill(0)),gl.DYNAMIC_DRAW);
      R.nN=R.gvNRows.length/13;}}
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.gvIdx);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,out.subarray(0,Math.max(2,n)),gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.gvGrid);gl.bufferData(gl.ARRAY_BUFFER,gr.subarray(0,Math.max(12,ng)),gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.gvX);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(X.length?X:new Array(10).fill(0)),gl.DYNAMIC_DRAW);
  for(const R of MODELS){if(!R.gvVao)continue;
    gl.bindBuffer(gl.ARRAY_BUFFER,R.gvInst);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(R.gvRows.length?R.gvRows:new Array(12).fill(0)),gl.DYNAMIC_DRAW);
    R.gvN=R.gvRows.length/12;}
}
// Line programs. Every line end carries the line's other end (aOther), so a line running
// behind the camera is cut where it crosses the near plane: some WebGL line rasterizers
// drop a line with an end behind the camera instead of cutting it, and a wall's outline
// often does. Both ends are first pulled a hair toward the camera (uPull) so r_showtris 1
// isn't lost in the very faces it outlines. A model's lines go through each instance's
// placement (aR0..aR2); the routes' through the distance test of the node they belong to.
const GV_CLIP=`
vec4 clipEnd(vec3 p,vec3 q){
  p=uEye+(p-uEye)*(1.0-uPull);q=uEye+(q-uEye)*(1.0-uPull);
  vec4 a=uVP*vec4(p,1.0),b=uVP*vec4(q,1.0);
  float da=a.z+a.w,db=b.z+b.w;
  if(da<0.0&&db>0.0)a=mix(a,b,min(1.0,da/(da-db)+1e-5));
  return a;}`;
const VS_GVL=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aOther; layout(location=7) in vec4 aCol;
uniform mat4 uVP; uniform vec3 uEye; uniform float uPull;
out vec4 vC;`+GV_CLIP+`
void main(){vC=aCol;gl_Position=clipEnd(aPos,aOther);}`;
const VS_GVLM=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aOther; layout(location=7) in vec4 aCol;
layout(location=3) in vec4 aR0; layout(location=4) in vec4 aR1; layout(location=5) in vec4 aR2;
uniform mat4 uVP; uniform vec3 uEye; uniform float uPull;
out vec4 vC;`+GV_CLIP+`
vec3 placed(vec3 v){vec4 h=vec4(v,1.0);return vec3(dot(aR0,h),dot(aR1,h),dot(aR2,h));}
void main(){vC=aCol;gl_Position=clipEnd(placed(aPos),placed(aOther));}`;
let PGVL=null,PGVLM=null;
function gvLineVAO(buf,withCol){
  const v=gl.createVertexArray();gl.bindVertexArray(v);const st=withCol?40:24;
  attr(0,buf,3,st,0);attr(1,buf,3,st,12);if(withCol)attr(7,buf,4,st,24);else gl.disableVertexAttribArray(7);
  return v;}
function gvGL(){
  if(B.gvIdx)return;
  PGVL=compile(VS_GVL,FS_LINE);PGVLM=compile(VS_GVLM,FS_LINE);
  // the fixed list: every surface line, then every terrain line, as (end, other end) pairs
  const G=GV,P=G.v,L=G.l,T=G.terLines,S=SC.pos,nw=L.length,out=new Float32Array(Math.max(6,(nw+T.length)*6));
  for(let m=0;m<nw;m++){const i=L[m],j=L[m^1];out.set([P[i*3],P[i*3+1],P[i*3+2],P[j*3],P[j*3+1],P[j*3+2]],m*6);}
  for(let m=0;m<T.length;m++){const i=T[m],j=T[m^1];out.set([S[i*3],S[i*3+1],S[i*3+2],S[j*3],S[j*3+1],S[j*3+2]],(nw+m)*6);}
  B.gvS=makeBuf(gl.ARRAY_BUFFER,out);
  B.gvIdx=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(2),gl.DYNAMIC_DRAW);
  B.vGvS=gvLineVAO(B.gvS,false);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.gvIdx);gl.bindVertexArray(null);
  B.gvGrid=makeBuf(gl.ARRAY_BUFFER,new Float32Array(12),gl.DYNAMIC_DRAW);
  B.vGvG=gvLineVAO(B.gvGrid,false);gl.bindVertexArray(null);
  B.gvX=makeBuf(gl.ARRAY_BUFFER,new Float32Array(10),gl.DYNAMIC_DRAW);
  B.vGvX=gvLineVAO(B.gvX,true);gl.bindVertexArray(null);
  // each model's triangles as lines (the surfaces it is drawn with close up)
  for(const R of MODELS){
    if(!R.inst.length)continue;
    const nv=R.pos.length/3,seen=new Set(),Lm=[],Q=R.pos;
    for(const s of R.surfs){if(s.sprite||s.lod)continue;
      for(let k=s.first;k+2<s.first+s.count;k+=3){const t=[R.idx[k],R.idx[k+1],R.idx[k+2]];
        for(let j=0;j<3;j++){let a=t[j],b=t[(j+1)%3];if(a>b){const x=a;a=b;b=x;}const key=a*nv+b;
          if(!seen.has(key)){seen.add(key);Lm.push(Q[a*3],Q[a*3+1],Q[a*3+2],Q[b*3],Q[b*3+1],Q[b*3+2],Q[b*3],Q[b*3+1],Q[b*3+2],Q[a*3],Q[a*3+1],Q[a*3+2]);}}}}
    if(!Lm.length)continue;
    R.gvLine=makeBuf(gl.ARRAY_BUFFER,new Float32Array(Lm));R.gvVerts=Lm.length/6;
    R.gvInst=gl.createBuffer();R.gvN=0;
    R.gvVao=gvLineVAO(R.gvLine,false);
    gl.bindBuffer(gl.ARRAY_BUFFER,R.gvInst);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(12),gl.DYNAMIC_DRAW);
    for(let k=0;k<3;k++){gl.enableVertexAttribArray(3+k);gl.vertexAttribPointer(3+k,4,gl.FLOAT,false,48,k*16);gl.vertexAttribDivisor(3+k,1);}
    gl.bindVertexArray(null);
  }
  G.dirty=true;
}
function gvUniforms(p,vp,pull){gl.useProgram(p);gl.uniformMatrix4fv(p.u.uVP,false,vp);gl.uniform3fv(p.u.uEye,cam.pos);
  gl.uniform1f(p.u.uPull,pull);gl.uniform1f(p.u.uAlpha,1);}
function drawShowTris(vp){
  const m=CVARS.r_showtris|0;
  if(!m||!GV||!gl)return;
  gvGL();gvUpdate();
  gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);gl.depthMask(false);
  // 1: hidden behind what is drawn (pulled a hair toward the camera); 2 and 3: on top of
  // everything (the engine draws them with the depth range squeezed to the near end)
  if(m===1){gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);}else gl.disable(gl.DEPTH_TEST);
  const pull=m===1?0.0015:0;
  gl.vertexAttrib4f(7,1,1,1,1);                 // white, as DrawTris
  if(m<3){
    gvUniforms(PGVL,vp,pull);
    if(GV.nIdx){gl.bindVertexArray(B.vGvS);gl.drawElements(gl.LINES,GV.nIdx,gl.UNSIGNED_INT,0);}
    if(GV.nGrid){gl.bindVertexArray(B.vGvG);gl.drawArrays(gl.LINES,0,GV.nGrid);}
    gvUniforms(PGVLM,vp,pull);
    for(const R of MODELS){if(!R.gvVao||!R.gvN)continue;gl.bindVertexArray(R.gvVao);
      gl.drawArraysInstanced(gl.LINES,0,R.gvVerts,R.gvN);}
  }
  if(m>1&&GV.nX){gvUniforms(PGVL,vp,0);gl.bindVertexArray(B.vGvX);gl.drawArrays(gl.LINES,0,GV.nX);}
  gl.bindVertexArray(null);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);
}

// ============================================================================
//  r_shownormals: a line along the normal of each point drawn (tr_shade.c DrawNormals)
// ============================================================================
// RB_EndSurface runs DrawNormals on every batch it draws, as DrawTris, so the points are
// r_showtris's: the faces, triangle soups and patch rows and columns gvUpdate keeps, and
// the models it lists (at their full detail). Each gets a white line 2 units long from the
// point along the normal the tessellator holds for it, over everything (the depth range
// squeezed to the near end): a face's plane, a soup's own vertex normals, a patch's grid
// normals (MakeMeshNormals), a model's vertex normal turned by its first weight's bone.
// An entity's lines are 2 world units (RB_SkelMesh scales its points, not the normals); a
// static prop's are 2 of its own units, so its scale stretches them (R_RotateForStaticModel
// puts the scale in the matrix). Terrain has none: tr_terrain.c never fills them in. In
// game a face or patch fills its normals in only when its shader uses them or a dynamic
// light is in the scene (RB_SurfaceFace, RB_SurfaceGrid); here each always shows its own.
const VS_GVN=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in float aEnd; layout(location=7) in vec4 aCol;
layout(location=3) in vec4 aR0; layout(location=4) in vec4 aR1; layout(location=5) in vec4 aR2; layout(location=6) in float aK;
uniform mat4 uVP; uniform vec3 uEye; uniform float uPull;
out vec4 vC;`+GV_CLIP+`
void main(){vC=aCol;vec4 h=vec4(aPos,1.0);
  vec3 p=vec3(dot(aR0,h),dot(aR1,h),dot(aR2,h)),q=p+vec3(dot(aR0.xyz,aNrm),dot(aR1.xyz,aNrm),dot(aR2.xyz,aNrm))*aK;
  gl_Position=aEnd<0.5?clipEnd(p,q):clipEnd(q,p);}`;
let PGVN=null;
// point v of G.v's line, both ends (each with the other end), 12 floats from out[k]
function gvNrmLine(G,out,v,k){const P=G.v,N=G.vn,i=v*3;
  const x=P[i],y=P[i+1],z=P[i+2],qx=x+2*N[i],qy=y+2*N[i+1],qz=z+2*N[i+2];
  out[k]=x;out[k+1]=y;out[k+2]=z;out[k+3]=qx;out[k+4]=qy;out[k+5]=qz;
  out[k+6]=qx;out[k+7]=qy;out[k+8]=qz;out[k+9]=x;out[k+10]=y;out[k+11]=z;}
// Made the first time the cvar is on, from where the points are then (a door may be open):
// a line for every point of G.v, and for each model one per vertex of the surfaces
// r_showtris outlines, placed by its instances with the line's length (aK) beside them.
function gvNrmGL(){
  const G=GV;if(B.gvN||!G||!G.vn)return;
  const nv=G.v.length/3,out=new Float32Array(Math.max(12,nv*12));
  for(let v=0;v<nv;v++)gvNrmLine(G,out,v,v*12);
  B.gvN=makeBuf(gl.ARRAY_BUFFER,out,gl.DYNAMIC_DRAW);
  gl.bindVertexArray(null);
  B.gvNIdx=makeBuf(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(2),gl.DYNAMIC_DRAW);
  B.vGvN=gvLineVAO(B.gvN,false);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.gvNIdx);gl.bindVertexArray(null);
  PGVN=compile(VS_GVN,FS_LINE);
  for(const R of MODELS){
    if(!R.inst.length||R.M.n==null)continue;
    const N=D.nrm(R.M.n),Q=R.pos,ss=R.surfs.filter(s=>!s.sprite&&!s.lod);
    let cnt=0;for(const s of ss)cnt+=s.vn;
    if(!cnt)continue;
    const L=new Float32Array(cnt*14);let k=0;
    for(const s of ss)for(let v=s.v0;v<s.v0+s.vn;v++){const i=v*3;
      for(let e=0;e<2;e++){L[k]=Q[i];L[k+1]=Q[i+1];L[k+2]=Q[i+2];L[k+3]=N[i];L[k+4]=N[i+1];L[k+5]=N[i+2];L[k+6]=e;k+=7;}}
    R.nLine=makeBuf(gl.ARRAY_BUFFER,L);R.nVerts=cnt*2;R.nInst=gl.createBuffer();R.nN=0;R.gvNRows=[];
    const v=gl.createVertexArray();gl.bindVertexArray(v);
    attr(0,R.nLine,3,28,0);attr(1,R.nLine,3,28,12);attr(2,R.nLine,1,28,24);gl.disableVertexAttribArray(7);
    gl.bindBuffer(gl.ARRAY_BUFFER,R.nInst);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(13),gl.DYNAMIC_DRAW);
    for(let k=0;k<3;k++){gl.enableVertexAttribArray(3+k);gl.vertexAttribPointer(3+k,4,gl.FLOAT,false,52,k*16);gl.vertexAttribDivisor(3+k,1);}
    gl.enableVertexAttribArray(6);gl.vertexAttribPointer(6,1,gl.FLOAT,false,52,48);gl.vertexAttribDivisor(6,1);
    gl.bindVertexArray(null);R.nVao=v;
  }
  G.dirty=true;                                  // the next update sends their lists
}
// points a..b-1 moved (a door): their lines again
function gvNrmSpan(G,a,b){
  if(!B.gvN||!G.vn||b<=a)return;
  const out=new Float32Array((b-a)*12);for(let v=a;v<b;v++)gvNrmLine(G,out,v,(v-a)*12);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.gvN);gl.bufferSubData(gl.ARRAY_BUFFER,a*48,out);}
function drawShowNormals(vp){
  if(!CVARS.r_shownormals||!GV||!GV.vn||!gl)return;
  gl.bindVertexArray(null);gvGL();gvNrmGL();gvUpdate();
  gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);gl.depthMask(false);gl.disable(gl.DEPTH_TEST);
  gl.vertexAttrib4f(7,1,1,1,1);                 // white, as DrawNormals
  if(GV.nNIdx){gvUniforms(PGVL,vp,0);gl.bindVertexArray(B.vGvN);gl.drawElements(gl.LINES,GV.nNIdx,gl.UNSIGNED_INT,0);}
  gvUniforms(PGVN,vp,0);
  for(const R of MODELS){if(!R.nVao||!R.nN)continue;gl.bindVertexArray(R.nVao);gl.drawArraysInstanced(gl.LINES,0,R.nVerts,R.nN);}
  gl.bindVertexArray(null);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);
}

// ============================================================================
//  ai_showroutes: the AI's path connections (navigate.cpp DrawAllConnections)
// ============================================================================
// From the map's .pth, the connections the game worked out between its path nodes (node i
// is the map's i-th info_pathnode, dropped to the floor). Every node within
// ai_showroutes_distance of the camera draws its connections 36 units up: a green line
// for each one the AI can take (a fall no higher than ai_fallheight), drawn once for a
// pair that connects both ways, and for a one-way connection a red arrowhead 16 units
// along it, pointing the way it goes; a node with no connections gets a red X on the
// floor, or a blue circle when it is marked not to be linked. Debug lines are hidden
// behind walls like the rest of the map.
let ROUTES=null;
const VS_ROUTE=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aOther; layout(location=7) in vec4 aCol; layout(location=8) in vec3 aNode;
uniform mat4 uVP; uniform vec3 uEye; uniform float uPull; uniform float uDist;
out vec4 vC;`+GV_CLIP+`
void main(){vC=aCol;
  if(distance(aNode,uEye)>uDist){gl_Position=vec4(2.0,2.0,2.0,1.0);return;}
  gl_Position=clipEnd(aPos,aOther);}`;
let PROUTE=null;
// The .pth is used only when it was made for this very map: the game checks the map_time
// stored in it against the .bsp's worldspawn "map_time" and builds its paths again when
// they differ (PathSearch::ArchiveLoadNodes), as for a copy Modify saved (bump_map_time)
// under the map's own name. Such a .pth is left out here too.
function pathsStale(){
  if(!(D.paths&&!D.paths.err&&D.paths.o!=null)||D.paths.time==null)return false;
  const mt=String((MAP.ents[0]&&MAP.ents[0].kvl.map_time)||'').trim();
  return !!mt&&String(D.paths.time).trim()!==mt;        // (a .map has none: it isn't compiled yet)
}
function pathsOk(){return !!(D.paths&&!D.paths.err&&D.paths.n>=0&&D.paths.o!=null)&&!pathsStale();}
// where AI routes come from, for the Output line when they are turned on
function routesFrom(){
  const nn=MOD.ents.filter(m=>!modIsMap(m)&&modIsNode(m)).length,plus=nn?' + '+nn+' new node'+(nn===1?'':'s')+' from Modify':'';
  if(pathsOk())return 'from '+(D.paths.src||'the map\'s .pth')+', '+D.paths.n+' nodes'+plus;
  if(pathsStale())return 'worked out here: '+(D.paths.src||'the .pth')+' is for another version of this map (its map_time "'+D.paths.time+
    '" isn\'t the .bsp\'s "'+((MAP.ents[0]&&MAP.ents[0].kvl.map_time)||'')+'"), so the game builds its paths again'+plus;
  return 'worked out here (no .pth for this map)'+plus;
}
// paths to draw: the .pth's, else the map's nodes worked out here (pgCreate), with MODIFY's
// new nodes added (PA)
function routesOk(){return pathsOk()||pnEnts().length>0||MOD.ents.some(modIsNode);}
function buildRoutes(){
  const A=routesOk()?PA():null;
  if(!A||!gl)return;
  const n=A.n,O=A.o,F=A.f,C=A.c,nc=C.length/9,fh=CVARS.ai_fallheight;
  const first=new Int32Array(n+1);
  for(let k=0;k<nc;k++){const i=C[k*9]|0;if(i>=0&&i<n)first[i+1]++;}
  for(let i=0;i<n;i++)first[i+1]+=first[i];
  const V=[];
  const line=(a,b,c,i)=>{const o=[O[i*3],O[i*3+1],O[i*3+2]];
    V.push(a[0],a[1],a[2],b[0],b[1],b[2],c[0],c[1],c[2],1,o[0],o[1],o[2], b[0],b[1],b[2],a[0],a[1],a[2],c[0],c[1],c[2],1,o[0],o[1],o[2]);};
  const G=[0,1,0],RED=[1,0,0],BLUE=[0,0,1];
  const tags=new Map();          // node -> {none, dl, ow}: what its red X / blue circle / red arrows say
  const tag=i=>{let t=tags.get(i);if(!t){t={none:false,dl:false,ow:0};tags.set(i,t);}return t;};
  for(let i=0;i<n;i++){
    const k0=first[i],k1=first[i+1];
    for(let k=k0;k<k1;k++){
      const q=k*9,to=C[q+1]|0,fall=C[q+2];
      if(fall>fh||to<0||to>=n)continue;
      let rev=false;
      for(let j=first[to+1]-1;j>=first[to];j--)if(C[j*9+2]<fh&&(C[j*9+1]|0)===i){rev=true;break;}
      if(!(i<to||!rev))continue;
      const p1=[C[q+3],C[q+4],C[q+5]+36],p2=[C[q+6],C[q+7],C[q+8]+36];
      line(p1,p2,G,i);
      if(!rev){
        tag(i).ow++;
        let dx=C[q+6]-C[q+3],dy=C[q+7]-C[q+4];const l=Math.hypot(dx,dy);if(l>0){dx/=l;dy/=l;}else{dx=0;dy=0;}
        const t=[p1[0]+dx*16,p1[1]+dy*16,p1[2]];
        line(t,[t[0]-dx*8,t[1]-dy*8,t[2]-8],RED,i);
        line(t,[t[0]-dx*8,t[1]-dy*8,t[2]+8],RED,i);
      }
    }
    if(k0===k1){
      const p=[O[i*3],O[i*3+1],O[i*3+2]+2];
      if(pnGone(A,i)){}                               // deleted in Modify: nothing to draw
      else if(F[i]&1){                                // PATH_DONT_LINK: a blue circle
        tag(i).dl=true;
        for(let s=0;s<24;s++){const a0=s*Math.PI/12,a1=(s+1)*Math.PI/12;
          line([p[0]+Math.sin(a0)*12,p[1]+Math.cos(a0)*12,p[2]],[p[0]+Math.sin(a1)*12,p[1]+Math.cos(a1)*12,p[2]],BLUE,i);}
      }else{
        tag(i).none=true;
        line([p[0]-12,p[1]-12,p[2]],[p[0]+12,p[1]+12,p[2]],RED,i);
        line([p[0]+12,p[1]-12,p[2]],[p[0]-12,p[1]+12,p[2]],RED,i);
      }
    }
  }
  if(!PROUTE)PROUTE=compile(VS_ROUTE,FS_LINE);
  if(!B.rtBuf){B.rtBuf=gl.createBuffer();B.vRt=gl.createVertexArray();gl.bindVertexArray(B.vRt);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.rtBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(13),gl.STATIC_DRAW);
    attr(0,B.rtBuf,3,52,0);attr(1,B.rtBuf,3,52,12);attr(7,B.rtBuf,4,52,24);attr(8,B.rtBuf,3,52,40);gl.bindVertexArray(null);}
  gl.bindBuffer(gl.ARRAY_BUFFER,B.rtBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(V.length?V:new Array(13).fill(0)),gl.STATIC_DRAW);
  ROUTES={verts:V.length/13,fh:fh,tags:tags,A:A};
}
function drawRoutes(vp){
  if(!CVARS.ai_showroutes||!routesOk()||!gl)return;
  if(!ROUTES||ROUTES.fh!==CVARS.ai_fallheight)buildRoutes();
  if(!ROUTES||!ROUTES.verts)return;
  gvUniforms(PROUTE,vp,0.0015);gl.uniform1f(PROUTE.u.uDist,CVARS.ai_showroutes_distance);
  gl.disable(gl.BLEND);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);
  gl.bindVertexArray(B.vRt);gl.drawArrays(gl.LINES,0,ROUTES.verts);
  gl.bindVertexArray(null);gl.depthMask(true);
}

// ============================================================================
//  Doors: Open door (O) opens a func_rotatingdoor or func_door as in game
// ============================================================================
// doors.cpp and mover.cpp. Each door keeps the game's states: closed, opening, open and
// closing. Open door does what the use key does (Door::DoorUse): a shut or closing door
// opens, an open or opening one closes. Doors of one class whose boxes touch (a unit
// apart) open and close as one, led by the first of them in the .map, the master
// (Door::LinkDoors); DOOR_DONT_LINK (4) keeps a door from leading others. A
// func_rotatingdoor turns "openangle" degrees (90) about its origin: with "alwaysaway" 1
// (the default) to the side away from whoever opens it, here the camera, and with 0
// always the same way, the side its box lies toward (RotatingDoor::DoOpen). A func_door
// slides along "angle" (-1 up, -2 down) by its size that way less "lip" (8). A move goes
// at an even speed from wherever the door is (Mover::MoveTo) and a whole one takes "time"
// seconds or "doortype" wood 1 / metal 1.5 (wood unless set), whichever key comes last;
// on a func_door "speed" (units a second) overrides both, on a func_rotatingdoor it is
// the rate itself (1 / time). Once open, the master closes the group "wait" seconds
// later (3; never with TOGGLE (32), or with "wait" -1 or 0). The master opens its area
// portal as it starts to open from shut and closes it once it is shut again, which
// r_showtris follows. A master that starts open (START_OPEN, 1) spawns with its portal
// open but stays where the .map has it, as in game, until it is closed. A script_door
// moves only when its map script tells it to, so it can't be opened here.
const DOOR_FRAME=50;                         // ms: one server frame (sv_fps 20), the shortest move
let DOORS=null;                              // entity -> door
const DOORS_BUSY=new Set();                  // doors with a move or an auto-close to come
const PORTAL_REF=new Map();                  // 'a1,a2' -> how many doors hold it open (CM_AdjustAreaPortalState)
function doorNum(v){const f=parseFloat(v);return isFinite(f)?f:0;}           // as atof
function doorMovedir(a){return a===-1?[0,0,1]:a===-2?[0,0,-1]:[Math.cos(a*Math.PI/180),Math.sin(a*Math.PI/180),0];}  // G_GetMovedir
function angleDist(a){a=((a%360)+360)%360;return a>180?a-360:a;}            // angledist: -180 .. 180
function doorsInit(){
  DOORS=new Map();DOORS_BUSY.clear();PORTAL_REF.clear();
  const byCls=new Map();
  for(let ei=1;ei<MAP.ents.length;ei++){
    const X=ENTS[ei],cls=MAP.ents[ei].cls;
    if(!DOOR_CLASSES[cls]||!X.hasGeo||!X.box)continue;
    const d=doorNew(ei);DOORS.set(ei,d);X.anchor0=X.anchor?X.anchor.slice():null;
    if(!byCls.has(cls))byCls.set(cls,[]);byCls.get(cls).push(d);
  }
  for(const list of byCls.values())doorsLink(list);
}
// A door's settings from its keys, in the order the game reads them (after its constructor:
// Door, RotatingDoor, SlidingDoor).
function doorNew(ei){
  const e=MAP.ents[ei],X=ENTS[ei],b=X.box,sf=parseInt(e.kvl.spawnflags||'0',10)|0;
  const kind=e.cls==='func_rotatingdoor'?'rot':e.cls==='func_door'?'slide':'script';
  const d={ei:ei,kind:kind,sf:sf,master:ei,next:-1,chain:[ei],state:(sf&1)?'open':'closed',prev:'',
    a:0,mv:null,closeAt:null,dirOpened:0,o:b.origin.slice(),mins:b.mins.slice(),maxs:b.maxs.slice(),
    how:'doortype wood, the default',wait:(sf&32)?0:3,waitKey:false,angle:90,away:true,lip:8,base:0,
    yawKey:0,dir:[0,1,0],move:[1,0,0],gm:null,reg:DOORS,busy:null,sim:false};   // reg/busy/sim: a copy the actors' walk plans on has its own (actDoorSim)
  d.prev=d.state;
  let rate=1;                                // Door::speed: 1 / traveltime
  for(const[k0,v]of e.kv){const k=k0.toLowerCase();
    if(k==='time'){const t=Math.max(DOOR_FRAME/1000,doorNum(v));rate=1/t;d.how='"time" '+fnum(t);}
    else if(k==='doortype'){if(v==='wood'||v==='metal'){rate=v==='wood'?1:1/1.5;d.how='doortype '+v;}}
    else if(k==='speed'){if(kind==='slide')d.base=doorNum(v);else{rate=doorNum(v);d.how='"speed" '+fnum(rate);}}
    else if(k==='wait'){d.wait=doorNum(v);d.waitKey=true;}
    else if(k==='openangle'&&kind==='rot')d.angle=doorNum(v);
    else if(k==='alwaysaway')d.away=(parseInt(v,10)|0)!==0;
    else if(k==='lip'&&kind==='slide')d.lip=doorNum(v);
    else if(k==='angle'){d.yawKey=doorNum(v);const m=doorMovedir(d.yawKey);d.move=m;d.dir=[-m[1],m[0],m[2]];}
  }
  // the way to the middle of its box from its origin
  d.mmo=vnorm([(d.mins[0]+d.maxs[0])/2,(d.mins[1]+d.maxs[1])/2,(d.mins[2]+d.maxs[2])/2])||[0,0,0];
  if(kind==='rot'){d.vel=Math.abs(rate*d.angle);d.full=Math.abs(angleDist(d.angle));}     // degrees a second
  else{const sz=[d.maxs[0]-d.mins[0],d.maxs[1]-d.mins[1],d.maxs[2]-d.mins[2]];
    d.total=Math.max(0,Math.abs(vdot(d.move,sz))-d.lip);                                // SlidingDoor::Setup
    if(d.base){rate=d.total?d.base/d.total:0;d.how='"speed" '+fnum(d.base);}
    d.vel=rate*d.total;d.full=d.total;}                                                   // units a second
  d.secs=Math.max(DOOR_FRAME/1000,d.vel>0?d.full/d.vel:0);
  return d;
}
// Door::DoorTouches, on the boxes the game links them with (a unit bigger all round)
function doorTouch(a,b){
  for(let k=0;k<3;k++){
    if(b.o[k]+b.mins[k]-1>a.o[k]+a.maxs[k]+1)return false;
    if(b.o[k]+b.maxs[k]+1<a.o[k]+a.mins[k]-1)return false;}
  return true;
}
// Door::LinkDoors, door by door in the .map's order: an unlinked door that some later door
// touches leads a chain of the touching doors after it; a door only an earlier door touches
// is left alone. A master that starts open opens its area portal.
function doorsLink(list){
  list.forEach((d,i)=>{
    if(d.next>=0)return;                     // linked by an earlier door
    d.master=d.ei;
    if(d.sf&4){d.next=d.ei;return;}          // DOOR_DONT_LINK
    let n=0;for(let j=i+1;j<list.length;j++)if(doorTouch(d,list[j]))n++;
    if(!n&&list.some(x=>x!==d&&doorTouch(d,x)))return;
    let ent=d;const chain=[];
    for(let j=i;j<list.length;j++){const x=list[j];
      if(!doorTouch(ent,x)||x.next>=0)continue;   // (a door linked twice stops the game: skipped)
      ent.next=x.ei;ent=x;x.master=d.ei;chain.push(x.ei);}
    ent.next=d.ei;d.chain=chain;
    if(d.sf&1)doorPortal(d,true);
  });
}
// The area portals the doors hold open, for r_showtris: each door's two areas (from where
// the .map has it), counted as the game counts them.
function doorPortal(d,open){
  if(d.sim)return;
  const a=GV&&GV.doorArea.get(d.ei);if(!a||a[0]<0||a[1]<0)return;
  const k=Math.min(a[0],a[1])+','+Math.max(a[0],a[1]);
  PORTAL_REF.set(k,(PORTAL_REF.get(k)||0)+(open?1:-1));
  GV.portals=[];for(const[key,n]of PORTAL_REF)if(n>0)GV.portals.push(key.split(',').map(Number));
  GV.key='';GV.skey='';GV.dirty=true;
}
// ---- the game's door events -------------------------------------------------------------
function doorShut(d){return d.state==='closed'||d.state==='closing';}
function doorOpen(d,t,from){                     // Door::Open; from: where the opener is
  if(d.state==='opening')return;
  if(d.state==='open'){if(d.wait>0){d.closeAt=t+d.wait*1000;(d.busy||DOORS_BUSY).add(d);}return;}   // waits its full time again
  d.prev=d.state;d.state='opening';
  if(d.kind==='rot'){                            // RotatingDoor::DoOpen (only a shut door picks its side)
    if(d.prev==='closed'){
      const px=from[0]-d.o[0],py=from[1]-d.o[1],l=Math.hypot(px,py),qx=l>0?px/l:0,qy=l>0?py/l:0;
      if(d.away){d.dirOpened=qx*d.dir[1]-qy*d.dir[0];if(vdot(d.dir,d.mmo)>0)d.dirOpened=-d.dirOpened;}
      else d.dirOpened=vdot(d.dir,d.mmo);
    }
    const to=d.dirOpened<0?d.angle:-d.angle;
    if(d.a+360<=to)d.a+=360;else if(d.a-360>=to)d.a-=360;
    doorMove(d,t,to,1);
  }else doorMove(d,t,d.total,1);                 // SlidingDoor::DoOpen
  if(d.master===d.ei){
    for(const s of d.chain)if(s!==d.ei)doorOpen(d.reg.get(s),t,from);
    if(d.prev==='closed')doorPortal(d,true);
  }
}
function doorMove(d,t,to,end){                   // Mover::MoveTo: an even speed, from where it is
  const delta=d.kind==='rot'?angleDist(to-d.a):to-d.a;
  let dur=d.vel>0?Math.abs(delta)/d.vel*1000:0, snap=false;
  if(dur<DOOR_FRAME){dur=DOOR_FRAME;snap=true;}  // nothing to do, or quicker than a frame: there at the frame's end
  d.mv={a0:d.a,a1:d.a+delta,to:to,t0:t,t1:t+dur,end:end,snap:snap};
  (d.busy||DOORS_BUSY).add(d);
}
function doorOpenEnd(d,t){                       // Door::OpenEnd
  d.prev=d.state;d.state='open';
  if(d.sf&32)return;                             // TOGGLE: it waits to be used again
  if(d.wait>0&&d.master===d.ei){d.closeAt=t+d.wait*1000;(d.busy||DOORS_BUSY).add(d);}
}
function doorClose(d,t){                         // Door::Close
  d.closeAt=null;
  d.prev=d.state;d.state='closing';
  doorMove(d,t,0,2);                             // back to its start angle or position
  if(d.master===d.ei)for(const s of d.chain)if(s!==d.ei)doorClose(d.reg.get(s),t);
}
function doorCloseEnd(d,t){                      // Door::CloseEnd
  if(d.master===d.ei)doorPortal(d,false);
  d.prev=d.state;d.state='closed';
}
// Run the doors up to now (ms): the moves that end and the closes that fall due, each at
// its own time (so a page left in the background catches up in order), then where each
// moving door is. True when anything changed.
function doorsAdvance(now,busy){                 // busy: a copy's own set (the actors' walk plan): nothing is drawn
  let changed=false,states=false;const BS=busy||DOORS_BUSY,sim=!!busy;
  for(;;){
    let d=null,at=Infinity,close=false;
    for(const x of BS){
      if(x.mv&&x.mv.t1<=now&&x.mv.t1<at){d=x;at=x.mv.t1;close=false;}
      if(x.closeAt!=null&&x.closeAt<=now&&x.closeAt<at){d=x;at=x.closeAt;close=true;}
    }
    if(!d)break;
    changed=states=true;
    if(close){d.closeAt=null;doorClose(d,at);}
    else{const m=d.mv;d.mv=null;d.a=m.to;if(!sim)doorPose(d);(m.end===1?doorOpenEnd:doorCloseEnd)(d,at);}
  }
  for(const d of [...BS]){
    if(d.mv&&!d.mv.snap){const m=d.mv,a=m.a0+(m.a1-m.a0)*Math.min(1,Math.max(0,(now-m.t0)/(m.t1-m.t0)));
      if(a!==d.a){d.a=a;if(!sim)doorPose(d);changed=true;}}
    if(!d.mv&&d.closeAt==null)BS.delete(d);
  }
  if(states&&!sim)doorBtnRender();
  return changed;
}
// ---- where a door is now ----------------------------------------------------------------
// A turn about its origin by yaw degrees (func_rotatingdoor) or a shift along its "angle"
// (func_door); null for a door where the .map has it.
function doorXf(ei){
  if(EXP.mov.size){const c=EXP.mov.get(ei);if(c)return c.xf;}
  const d=DOORS&&DOORS.get(ei);if(!d||!d.a)return null;
  return doorXfAt(d,d.a);
}
function doorXfAt(d,a){
  if(d.kind==='rot'){const r=a*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return{R:[c,-s,0,s,c,0,0,0,1],o:d.o,t:[0,0,0],yaw:a};}
  return{R:[1,0,0,0,1,0,0,0,1],o:d.o,t:[d.move[0]*a,d.move[1]*a,d.move[2]*a],yaw:0};
}
function xfP(X,p){const o=X.o,R=X.R,x=p[0]-o[0],y=p[1]-o[1],z=p[2]-o[2];
  return[o[0]+X.t[0]+R[0]*x+R[1]*y+R[2]*z,o[1]+X.t[1]+R[3]*x+R[4]*y+R[5]*z,o[2]+X.t[2]+R[6]*x+R[7]*y+R[8]*z];}
function xfN(X,n){const R=X.R;return[R[0]*n[0]+R[1]*n[1]+R[2]*n[2],R[3]*n[0]+R[4]*n[1]+R[5]*n[2],R[6]*n[0]+R[7]*n[1]+R[8]*n[2]];}
// positions src (where the .map has them) put into dst from float k on, moved by X
function xfSpan(X,src,dst,k){
  if(!X){dst.set(src,k);return;}
  const o=X.o,R=X.R,tx=o[0]+X.t[0],ty=o[1]+X.t[1],tz=o[2]+X.t[2];
  for(let i=0;i<src.length;i+=3){const x=src[i]-o[0],y=src[i+1]-o[1],z=src[i+2]-o[2];
    dst[k+i]=tx+R[0]*x+R[1]*y+R[2]*z;dst[k+i+1]=ty+R[3]*x+R[4]*y+R[5]*z;dst[k+i+2]=tz+R[6]*x+R[7]*y+R[8]*z;}
}
// the eight corners of a door's box (origin + setsize), corner k as in boxLines, moved by X
function doorCorners(d,X){const o=d.o,out=[];
  for(let k=0;k<8;k++){const p=[o[0]+((k&1)?d.maxs[0]:d.mins[0]),o[1]+((k&2)?d.maxs[1]:d.mins[1]),o[2]+((k&4)?d.maxs[2]:d.mins[2])];
    out.push(X?xfP(X,p):p);}
  return out;}
function ptsBounds(pts){const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  for(const p of pts)for(let k=0;k<3;k++){if(p[k]<mn[k])mn[k]=p[k];if(p[k]>mx[k])mx[k]=p[k];}
  return{mins:mn,maxs:mx};}
function runsOf(sorted){const out=[];for(const v of sorted){const r=out[out.length-1];if(r&&r[1]===v)r[1]++;else out.push([v,v+1]);}return out;}
// The parts of a door that move, each with a copy of where the .map has it: its .map faces
// (one run of vertices), the game's polygons for it (LIT) and its r_showtris surfaces.
function doorGeom(d){
  if(d.gm)return d.gm;
  const g={prims:primsOfEnt(d.ei),faces:[],pl:[],sc:null,lit:[],gv:null};
  let v0=Infinity,v1=-Infinity;
  for(const pi of g.prims){const p=SC.prims[pi];
    for(let f=p.f0;f<p.f1;f++){g.faces.push(f);g.pl.push(SC.facePlane[f]?SC.facePlane[f].slice():null);
      v0=Math.min(v0,SC.faceV0[f]);v1=Math.max(v1,SC.faceV0[f]+SC.faceVN[f]);}}
  if(v0<v1)g.sc={v0:v0,v1:v1,P:SC.pos.slice(v0*3,v1*3)};
  if(LIT){const vs=new Set();for(const u of LIT.units)if(u.ei===d.ei)for(let k=u.i0;k<u.i0+u.n;k++)vs.add(LIT.tri[k]);
    g.lit=runsOf([...vs].sort((a,b)=>a-b)).map(([a,b])=>({v0:a,v1:b,P:LIT.pos.slice(a*3,b*3)}));}
  const G=GV,R=G&&G.bm.get(d.ei);
  if(R){const S=[];let p0=Infinity,p1=-Infinity,l0=Infinity,l1=-Infinity;
    for(let r=0;r<R.length;r+=2)for(let s=R[r];s<R[r]+R[r+1]&&s<G.ns;s++){
      const o=s*8,k=G.si[o];if(!k)continue;let a=Infinity,b=-Infinity;
      if(k===3){a=G.si[o+3];b=a+G.si[o+4]*G.si[o+5];}
      else{const m0=G.si[o+3],mc=G.si[o+4];
        for(let m=m0;m<m0+mc;m++){const v=G.l[m];if(v<a)a=v;if(v+1>b)b=v+1;}
        if(G.si[o+6]>0){a=Math.min(a,G.si[o+5]);b=Math.max(b,G.si[o+5]+G.si[o+6]);}   // all its points (r_shownormals)
        if(mc){l0=Math.min(l0,m0);l1=Math.max(l1,m0+mc);}}
      if(!(a<b))continue;
      S.push({s:s,k:k,a:a,b:b,f:G.sf.slice(s*10,s*10+10)});p0=Math.min(p0,a);p1=Math.max(p1,b);}
    if(S.length)g.gv={S:S,p0:p0,p1:p1,P:G.v.slice(p0*3,p1*3),N:G.vn?G.vn.slice(p0*3,p1*3):null,l0:l0,l1:l1};}
  return d.gm=g;
}
// Put a door where it is now (d.a): its faces, with the planes and boxes that picking and
// the see-through test read, the game's polygons and r_showtris's surfaces; its box,
// label and links follow on the next frame.
function doorPose(d){entPose(d,doorXf(d.ei));}
// Put a brush entity's geometry where transform X has it (null: where the .map has it): a
// door (doorPose) or a flying exploder chunk (expPose); d has the entity (ei), its origin
// and box (o, mins, maxs) and a cache for its geometry (gm).
function entPose(d,X){
  if(!gl)return;
  const g=doorGeom(d);
  if(g.sc){const s=g.sc;xfSpan(X,s.P,SC.pos,s.v0*3);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.pos);gl.bufferSubData(gl.ARRAY_BUFFER,s.v0*12,SC.pos.subarray(s.v0*3,s.v1*3));}
  g.faces.forEach((f,i)=>{const p=g.pl[i];if(!p)return;
    if(!X){SC.facePlane[f]=p.slice();return;}
    const n=xfN(X,p),q=xfP(X,[p[0]*p[3],p[1]*p[3],p[2]*p[3]]);SC.facePlane[f]=[n[0],n[1],n[2],vdot(n,q)];});
  for(const pi of g.prims){const p=SC.prims[pi],mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(let f=p.f0;f<p.f1;f++)for(let v=SC.faceV0[f],ve=v+SC.faceVN[f];v<ve;v++)
      for(let k=0;k<3;k++){const w=SC.pos[v*3+k];if(w<mn[k])mn[k]=w;if(w>mx[k])mx[k]=w;}
    if(isFinite(mn[0])){p.mins=mn;p.maxs=mx;}}
  if(g.lit.length){gl.bindBuffer(gl.ARRAY_BUFFER,B.lPos);
    for(const s of g.lit){xfSpan(X,s.P,LIT.pos,s.v0*3);gl.bufferSubData(gl.ARRAY_BUFFER,s.v0*12,LIT.pos.subarray(s.v0*3,s.v1*3));}}
  if(g.gv)doorGv(d,g.gv,X);
  const E=ENTS[d.ei];if(E.anchor0)E.anchor=X?xfP(X,E.anchor0):E.anchor0.slice();
  lineDirty=true;
}
// r_showtris: the door's points, its faces' planes (the facing-away test), patch centres
// and boxes, its lines (when already uploaded), and the server's link of it, from the
// box its turned setsize makes (SV_LinkEntity: CalculateRotatedBounds2).
function doorGv(d,gg,X){
  const G=GV;
  xfSpan(X,gg.P,G.v,gg.p0*3);
  // r_shownormals: its normals turned with it, and their lines when already uploaded
  if(gg.N&&G.vn){const N=gg.N,k0=gg.p0*3;
    for(let i=0;i<N.length;i+=3){const r=X?xfN(X,[N[i],N[i+1],N[i+2]]):[N[i],N[i+1],N[i+2]];G.vn[k0+i]=r[0];G.vn[k0+i+1]=r[1];G.vn[k0+i+2]=r[2];}
    gvNrmSpan(G,gg.p0,gg.p1);}
  for(const S of gg.S){const q=S.s*10,f=S.f;
    if(!X){G.sf.set(f,q);continue;}
    if(S.k===1){const n=xfN(X,f),p=xfP(X,[f[0]*f[3],f[1]*f[3],f[2]*f[3]]);G.sf[q]=n[0];G.sf[q+1]=n[1];G.sf[q+2]=n[2];G.sf[q+3]=vdot(n,p);}
    else if(S.k===3){const c=xfP(X,[f[0],f[1],f[2]]);G.sf[q]=c[0];G.sf[q+1]=c[1];G.sf[q+2]=c[2];}
    const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(let v=S.a;v<S.b;v++)for(let k=0;k<3;k++){const w=G.v[v*3+k];if(w<mn[k])mn[k]=w;if(w>mx[k])mx[k]=w;}
    G.sf.set(mn,q+4);G.sf.set(mx,q+7);}
  if(B.gvS&&gg.l1>gg.l0){const P=G.v,L=G.l,out=new Float32Array((gg.l1-gg.l0)*6);
    for(let m=gg.l0;m<gg.l1;m++){const i=L[m]*3,j=L[m^1]*3,k=(m-gg.l0)*6;
      out[k]=P[i];out[k+1]=P[i+1];out[k+2]=P[i+2];out[k+3]=P[j];out[k+4]=P[j+1];out[k+5]=P[j+2];}
    gl.bindBuffer(gl.ARRAY_BUFFER,B.gvS);gl.bufferSubData(gl.ARRAY_BUFFER,gg.l0*24,out);}
  const b=ptsBounds(doorCorners(d,X));gvLink(G,d.ei,b.mins,b.maxs);
  G.dirty=true;
}
// ---- Open door: the Selection button and O ----------------------------------------------
function selDoors(){const out=[];if(DOORS)for(const ei of selectedEnts()){const d=DOORS.get(ei);if(d)out.push(d);}return out;}
function doorWay(d){return d.move[2]>0.5?'up':d.move[2]<-0.5?'down':'toward yaw '+fnum(d.yawKey);}
function doorCloses(m){
  if(m.sf&32)return 'it stays open until it is used again (TOGGLE)';
  if(m.wait>0)return 'it closes by itself '+fnum(m.wait)+' s after it has opened';
  return 'it stays open ("wait" '+fnum(m.wait)+')';
}
function doorTip(d,m,opening){
  if(!opening)return 'Close it, as the use key does in game (O)';
  let s='Open it as in game: it '+(d.kind==='rot'?'swings '+fnum(d.full)+'° '+(d.away?'away from the camera':'always the same way ("alwaysaway" 0)'):
    'slides '+fnum(d.total)+' units '+doorWay(d))+' in '+fnum(d.secs)+' s';
  if(m.chain.length>1)s+=', with the '+(m.chain.length-1)+' door'+(m.chain.length>2?'s':'')+' linked to it';
  s+='; '+doorCloses(m);
  const by=doorOpener(d);if(by!=='the use key')s+='. In game it is opened by '+by;
  return s+' (O)';
}
function doorBtnRender(){
  const b=$('bDoor');if(!b)return;
  const ds=selDoors();
  if(!ds.length){b.style.display='none';return;}
  b.style.display='';
  const mv=ds.filter(d=>d.kind!=='script');
  if(!mv.length){b.disabled=true;b.textContent='Open door';
    b.title='A script_door moves only when its map script tells it to (its openthread and closethread), so it can\'t be opened here';return;}
  const ms=[...new Set(mv.map(d=>DOORS.get(d.master)))], opening=ms.some(doorShut);
  const txt=(opening?'Open':'Close')+' door'+(ms.length>1?'s':''),
    tip=ms.length>1?(opening?'Open':'Close')+' the '+ms.length+' selected doors as in game (O)':doorTip(mv[0],ms[0],opening);
  b.disabled=false;if(b.textContent!==txt)b.textContent=txt;if(b.title!==tip)b.title=tip;
}
// Open door: what the use key does (DoorUse to the master, then DoorFire): shut or closing
// doors open, from where the camera is; when every one is open or opening, they close.
function doorUse(){
  const all=selDoors(),ds=all.filter(d=>d.kind!=='script');
  if(!ds.length){flash(all.length?'A script_door moves only when its map script tells it to, so it can\'t be opened here':
    'Select a func_rotatingdoor or func_door first: O opens and closes it');return;}
  const now=performance.now();doorsAdvance(now);
  const ms=[...new Set(ds.map(d=>DOORS.get(d.master)))], opening=ms.some(doorShut);
  for(const m of ms){if(opening)doorOpen(m,now,cam.pos);else{m.sf&=~1;doorClose(m,now);}}
  doorBtnRender();requestDraw();
  if(ms.length===1){const m=ms[0],n=m.chain.length-1;
    flash((opening?'Opening ':'Closing ')+entName(ds[0].ei)+(n?' and the '+n+' door'+(n>1?'s':'')+' linked to it':'')+(opening?' · '+doorCloses(m):''));}
  else flash((opening?'Opening ':'Closing ')+ms.reduce((s,m)=>s+m.chain.length,0)+' doors');
}
// the Door part of a door's info card
function doorOpener(d){
  const hp=doorNum(MAP.ents[d.ei].kvl.health);
  let s=hp?'being shot (health '+fnum(hp)+')':(d.sf&128)?'a trigger or script only (TARGETED)':(d.sf&64)?'a player coming near it (AUTO_OPEN)':'the use key';
  if(d.sf&8)s+=', not players (NOT_PLAYERS)';
  if(d.sf&16)s+=', not AI (NOT_MONSTERS)';
  return s;
}
function doorInfo(ei){
  const d=DOORS&&DOORS.get(ei);if(!d)return '';
  let h='<h4>Door</h4>';
  if(d.kind==='script')return h+'<div class="note">A script_door moves only when its map script tells it to (its initthread, openthread and closethread keys), so Open door can\'t move it here.</div>';
  const m=DOORS.get(d.master),rows=[];
  rows.push(['opens',esc(d.kind==='rot'?'swings '+fnum(d.full)+'° about its origin, '+(d.away?'away from whoever opens it ("alwaysaway" 1, the default)':'always to the same side ("alwaysaway" 0)'):
    'slides '+fnum(d.total)+' units '+doorWay(d)+' (its size that way, less "lip" '+fnum(d.lip)+')')]);
  rows.push(['takes',esc(fnum(d.secs)+' s ('+d.how+')')]);
  rows.push(['closes',esc((m.sf&32)?'only when it is used again (TOGGLE)':m.wait>0?fnum(m.wait)+' s after it has opened ('+(m.waitKey?'"wait"':'the default "wait"')+')':
    'never by itself ("wait" '+fnum(m.wait)+')')]);
  rows.push(['opened by',esc(doorOpener(d))]);
  if(m.chain.length>1)rows.push(['linked',d.master===ei?'it leads '+m.chain.filter(x=>x!==ei).map(linkEnt).join(', ')+': they open and close together':
    'it opens and closes with '+linkEnt(m.ei)+', the master (the first of the touching doors in the .map)']);
  const a=GV&&GV.doorArea.get(m.ei);
  if(a&&a[0]>=0&&a[1]>=0)rows.push(['area portal',esc('joins areas '+a[0]+' and '+a[1]+' while it is open (r_showtris)')]);
  return h+kvTable(rows)+'<div class="note">Open door (O) under Selection opens it the way the use key does in game, from where the camera is.</div>';
}

// ============================================================================
//  Exploders: Run exploder plays global/exploder.scr's "explode" for a #set
// ============================================================================
// global/exploder.scr (Mackey McCandlish's chunk system) as the game runs it, without its
// sounds and emitters. Every $exploder, $explodersmashed, $exploderchunk, $exploderfire and
// $explodertrigger has a "#set"; "explode #set" (an explodertrigger, or the map script)
// sets off every entity of that set, each after its own "#pause":
//  - an $exploder hides and goes notsolid (exploderOFF);
//  - an $explodersmashed shows and goes solid (explodersmashedON): here it is drawn all
//    the time (it usually sits inside its $exploder), so it is only solid from then on
//    for the chunks to land on;
//  - an $exploderchunk is thrown toward the script_origin it targets (explodechunk): its
//    velocity is the way from its origin to the target, the up part times 1.5, at first
//    as a mover (MOVETYPE_PUSH, through anything) and after 0.2 s with physics_on
//    (MOVETYPE_BOUNCE, G_Physics_Toss: gravity 800, a box trace against the solid world,
//    bouncing off at 1.4 with its sideways speed cut, stopping on a floor below 40 units a
//    second). It spins on its own axes (rotatex/y/z, degrees a second) by its keys or
//    else by random amounts about its longest way across, the spin dying away over 10 to
//    24 frames from 0.5 s on. The first thing it touches starts moveitout, which lowers
//    it by its fall speed / 15 a frame for 48 frames (into the ground). 10 s after the
//    spin stops it hides (the game deletes it).
//  - an $exploderfire would play its emitter: not shown here.
// The game's level.exploderrepeat is 0, so a set explodes once; Reset exploder puts it all
// back as the level starts. Nothing is hidden or shown at the start here: in game
// exploder.scr hides the smashed and the chunks as the level loads, but the viewer draws
// the map as the .bsp has it (obj_team2's chunks are seen, Hide hides any of them).
// "#" keys are script variables read as whole numbers (atoi in SpawnArgs::SpawnInternal):
// "#pause" ".1" is 0. Plain keys such as "anglex" "80" are not variables (an unknown
// command), so the spin is the random one.
const EXP_TN={exploder:'exploder',explodersmashed:'smashed',exploderchunk:'chunk',exploderfire:'fire',explodertrigger:'trigger'};
const EXP_FRAME=50;                          // ms: a server frame (sv_fps 20)
const EXP={sets:null,runs:new Map(),hid:new Set(),mov:new Map(),busy:new Set(),solid:null,grid:null};
function expKey(ei,k){                        // a "#" key as the game reads it: atoi, else NIL
  for(const[k0,v]of MAP.ents[ei].kv)if(k0.toLowerCase()==='#'+k){const n=parseInt(v,10);return isFinite(n)?n:0;}
  return null;}
function expRole(ei){const t=MAP.ents[ei]&&MAP.ents[ei].kvl.targetname;return t&&EXP_TN[t]||'';}
function expInit(){
  EXP.sets=new Map();EXP.runs.clear();EXP.hid.clear();EXP.mov.clear();EXP.busy.clear();EXP.solid=null;EXP.grid=null;
  for(let ei=1;ei<MAP.ents.length;ei++){const r=expRole(ei);if(!r)continue;
    const set=expKey(ei,'set');if(set==null)continue;
    let S=EXP.sets.get(set);if(!S){S={set:set,exploder:[],smashed:[],chunk:[],fire:[],trigger:[]};EXP.sets.set(set,S);}
    S[r].push(ei);}
}
// the sets the selection belongs to
function expSelSets(){const out=new Set();if(!EXP.sets)return out;
  for(const ei of selectedEnts()){if(!expRole(ei))continue;const s=expKey(ei,'set');if(s!=null&&EXP.sets.has(s))out.add(s);}
  return out;}
function rnd(n){return Math.random()*n;}                 // randomfloat
function rndi(n){return Math.floor(Math.random()*n);}     // randomint
// ---- running a set ----------------------------------------------------------------------
function expRun(set,now){
  const S=EXP.sets.get(set);if(!S||EXP.runs.has(set))return;
  const R={set:set,t0:now,k:0,exps:[],sm:[],chunks:[],done:false};
  const frames=ei=>{const p=expKey(ei,'pause');return p>0?Math.round(p*1000/EXP_FRAME):0;};
  for(const ei of S.exploder)R.exps.push({ei:ei,at:frames(ei),done:false});
  for(const ei of S.smashed)R.sm.push({ei:ei,at:frames(ei),on:false});
  for(const ei of S.chunk){const X=ENTS[ei];if(!X.hasGeo||!X.box)continue;
    R.chunks.push({ei:ei,at:frames(ei),st:'wait',o0:X.box.origin.slice(),o:X.box.origin.slice(),ang:[0,0,0],vel:[0,0,0],avel:[0,0,0],
      mins:X.box.mins.slice(),maxs:X.box.maxs.slice(),ground:false,touched:false,sink:0,sinkN:0,ks:0,inc:0,dec:null,hideAt:-1,
      d:{ei:ei,o:X.box.origin.slice(),mins:X.box.mins.slice(),maxs:X.box.maxs.slice(),gm:null}});}
  EXP.runs.set(set,R);EXP.busy.add(R);EXP.solid=null;
}
// The world's solid brushes, patches and terrain, and the solid brush entities, each a set
// of planes a box is traced through (CM_TraceThroughBrush); MASK_SOLID: CONTENTS_SOLID and
// CONTENTS_FENCE (no clips). A patch or terrain triangle is a thin prism. Bucketed on a
// 512-unit grid across x and y.
const EXP_CELL=512;
function expSolids(){
  if(EXP.grid)return EXP.grid;
  const L=[];
  const solidC=(cont,te)=>{let c=(cont|0)&~CONTENTS_DETAIL;if(!c)c=(te.cf|0)|((te.p||[]).some(x=>CLEARS_SOLID.has(x))?0:1);return (c&(1|0x2000))!==0;};
  const bevel=(pl,mn,mx)=>{pl.push([1,0,0,mx[0]],[-1,0,0,-mn[0]],[0,1,0,mx[1]],[0,-1,0,-mn[1]],[0,0,1,mx[2]],[0,0,-1,-mn[2]]);};
  const prism=(ei,a,b,c,two)=>{
    let n=vnorm(vcross(vsub(b,a),vsub(c,a)));if(!n)return;
    if(!two&&n[2]<0)n=[-n[0],-n[1],-n[2]];
    const d=vdot(n,a),T=two?1:16,pl=[];
    if(two){pl.push([n[0],n[1],n[2],d+T],[-n[0],-n[1],-n[2],-(d-T)]);}
    else pl.push([n[0],n[1],n[2],d],[-n[0],-n[1],-n[2],-(d-T)]);
    const P=[a,b,c];
    for(let i=0;i<3;i++){const p=P[i],q=P[(i+1)%3],r=P[(i+2)%3];let e=vnorm(vcross(vsub(q,p),n));if(!e)continue;
      if(vdot(e,vsub(r,p))>0)e=[-e[0],-e[1],-e[2]];pl.push([e[0],e[1],e[2],vdot(e,p)]);}
    const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(const p of P)for(const s of[-T,T])for(let k=0;k<3;k++){const v=p[k]+n[k]*s;if(v<mn[k])mn[k]=v;if(v>mx[k])mx[k]=v;}
    bevel(pl,mn,mx);L.push({ei:ei,mn:mn,mx:mx,pl:pl});};
  const pt=v=>[SC.pos[v*3],SC.pos[v*3+1],SC.pos[v*3+2]];
  for(const p of SC.prims){
    const e=MAP.ents[p.ent];if(!isFinite(p.mins[0])||e.cls.startsWith('trigger_'))continue;
    if(p.ent>0&&!WORLDLIKE[e.cls]&&(expRole(p.ent)==='chunk'||expRole(p.ent)==='trigger'))continue;
    const pr=e.prims[p.bn];if(!pr||!pr.d)continue;
    if(p.kind===0){const faces=pr.d.faces;if(!faces.length||!solidC(faces[0].cont,texFor(faces[0].tex)))continue;
      const pl=[];for(const f of faces){const q=planeOf(f);if(q)pl.push(q);}
      if(!pl.length)continue;bevel(pl,p.mins,p.maxs);
      L.push({ei:p.ent,mn:p.mins.slice(),mx:p.maxs.slice(),pl:pl});}
    else{
      if(p.kind===1&&!solidC(pr.d.cont,texFor(pr.d.tex)))continue;
      for(let f=p.f0;f<p.f1;f++){
        if(p.kind===2&&(TEX[SC.faceTex[f]].p||[]).some(x=>CLEARS_SOLID.has(x)))continue;
        const i0=SC.faceI0[f],n=SC.faceIN[f]/3;
        for(let t=0;t<n;t++){if(p.kind===1&&(t%4)>=2)continue;      // a patch's quads are listed both ways round
          const q=i0+t*3;prism(p.ent,pt(SC.tri[q]),pt(SC.tri[q+1]),pt(SC.tri[q+2]),p.kind===1);}}}
  }
  const cells=new Map();
  L.forEach((B,i)=>{const x0=Math.floor(B.mn[0]/EXP_CELL),x1=Math.floor(B.mx[0]/EXP_CELL),y0=Math.floor(B.mn[1]/EXP_CELL),y1=Math.floor(B.mx[1]/EXP_CELL);
    for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){const k=x+','+y;let c=cells.get(k);if(!c){c=[];cells.set(k,c);}c.push(i);}});
  return EXP.grid={L:L,cells:cells,stamp:new Uint32Array(L.length),sn:0};
}
// What a thrown chunk can hit now: the world, the func_ brush entities, every $exploder
// still standing and each $explodersmashed its set has shown. Not an $exploder that has
// gone (notsolid), a smashed one before its set goes off (exploder.scr makes them notsolid
// as the level loads), nor the chunks (physics_on 1 leaves MASK_SCRIPT_SLAVE out, and they
// are notsolid until then).
function expCanHit(ei){
  if(ei===0||WORLDLIKE[MAP.ents[ei].cls])return true;
  if(!EXP.solid){const sol=new Set(),gone=new Set();
    for(const R of EXP.runs.values()){for(const s of R.sm)if(s.on)sol.add(s.ei);for(const x of R.exps)if(x.done)gone.add(x.ei);}
    EXP.solid={sol:sol,gone:gone};}
  const r=expRole(ei);
  if(r==='smashed')return EXP.solid.sol.has(ei);
  if(r==='exploder')return !EXP.solid.gone.has(ei);
  // other script_objects are left out: map scripts often make them notsolid, hide or move
  // them (spawn detectors, scripted walls), which the viewer can't know; func_ doors and
  // walls are solid
  return r!=='chunk'&&MAP.ents[ei].cls.startsWith('func_');
}
// G_Trace of a box (mins, maxs about the origin) from s to e: CM_TraceThroughBrush with
// each plane moved out by the box's corner (SURFACE_CLIP_EPSILON 0.125). Returns the
// fraction, the plane met, whether it met the world, and whether it started (all) solid.
function expTrace(s,e,mins,maxs){
  const G=expSolids(),EPS=0.125,tr={f:1,n:null,world:false,startsolid:false,allsolid:false};
  const lo=[Math.min(s[0],e[0])+mins[0]-1,Math.min(s[1],e[1])+mins[1]-1,Math.min(s[2],e[2])+mins[2]-1],
        hi=[Math.max(s[0],e[0])+maxs[0]+1,Math.max(s[1],e[1])+maxs[1]+1,Math.max(s[2],e[2])+maxs[2]+1];
  const sn=++G.sn;
  const x0=Math.floor(lo[0]/EXP_CELL),x1=Math.floor(hi[0]/EXP_CELL),y0=Math.floor(lo[1]/EXP_CELL),y1=Math.floor(hi[1]/EXP_CELL);
  for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){const c=G.cells.get(x+','+y);if(!c)continue;
    for(const i of c){if(G.stamp[i]===sn)continue;G.stamp[i]=sn;const B=G.L[i];
      if(B.mn[0]>hi[0]||B.mx[0]<lo[0]||B.mn[1]>hi[1]||B.mx[1]<lo[1]||B.mn[2]>hi[2]||B.mx[2]<lo[2])continue;
      if(!expCanHit(B.ei))continue;
      let enter=-1,leave=1,clip=null,startout=false,getout=false,miss=false;
      for(const q of B.pl){
        const ox=q[0]<0?maxs[0]:mins[0],oy=q[1]<0?maxs[1]:mins[1],oz=q[2]<0?maxs[2]:mins[2];
        const dist=q[3]-(ox*q[0]+oy*q[1]+oz*q[2]);
        const d1=s[0]*q[0]+s[1]*q[1]+s[2]*q[2]-dist,d2=e[0]*q[0]+e[1]*q[1]+e[2]*q[2]-dist;
        if(d2>0)getout=true;
        if(d1>0)startout=true;
        if(d1>0&&(d2>=EPS||d2>=d1)){miss=true;break;}
        if(d1<=0&&d2<=0)continue;
        if(d1>d2){const f=(d1-EPS)/(d1-d2);if(f>enter){enter=f;clip=q;}}
        else{const f=(d1+EPS)/(d1-d2);if(f<leave)leave=f;}
      }
      if(miss)continue;
      if(!startout){tr.startsolid=true;if(!getout){tr.allsolid=true;tr.f=0;tr.n=null;tr.world=B.ei===0||!!WORLDLIKE[MAP.ents[B.ei].cls];return tr;}continue;}
      if(enter<leave&&enter>-1&&enter<tr.f){tr.f=Math.max(0,enter);tr.n=clip;tr.world=B.ei===0||!!WORLDLIKE[MAP.ents[B.ei].cls];}
    }}
  return tr;
}
// G_PushEntity: the box moved as far as the trace lets it
function expPush(c,mv){
  const s=c.o,e=[s[0]+mv[0],s[1]+mv[1],s[2]+mv[2]],t=expTrace(s,e,c.mins,c.maxs);
  c.o=[s[0]+mv[0]*t.f,s[1]+mv[1]*t.f,s[2]+mv[2]*t.f];
  if(t.f<1&&!c.touched){c.touched=true;            // explodetouch: moveitout self.velocity[2], its first step at once
    const num=c.vel[2]/15;c.sink=Math.abs(num);c.sinkN=48;expSink(c);}
  return t;
}
function expSink(c){if(c.sinkN>0){c.sinkN--;c.o[2]-=c.sink;}}
// one server frame of G_Physics_Toss (MOVETYPE_BOUNCE)
function expToss(c){
  const dt=EXP_FRAME/1000;
  if(c.vel[2]>0)c.ground=false;
  if(c.ground){for(let k=0;k<3;k++)c.ang[k]+=c.avel[k]*dt;c.vel=[0,0,0];return;}
  c.vel[2]-=800*dt;                                // G_AddGravity, sv_gravity 800
  for(let k=0;k<3;k++)c.ang[k]+=c.avel[k]*dt;
  const mv=[c.vel[0]*dt,c.vel[1]*dt,c.vel[2]*dt];
  const t=expPush(c,mv);
  if(t.f===0)expPush(c,[mv[0]*dt*15,mv[1]*dt*15,0]);       // slide
  if(t.f<1){
    const n=t.n||[0,0,0],b=(c.vel[0]*n[0]+c.vel[1]*n[1]+c.vel[2]*n[2])*1.4;   // G_ClipVelocity, overbounce 1.4
    for(let k=0;k<3;k++){c.vel[k]-=n[k]*b;if(c.vel[k]>-0.1&&c.vel[k]<0.1)c.vel[k]=0;}
    c.vel[0]-=c.vel[0]*dt*1.75;c.vel[1]-=c.vel[1]*dt*1.75;
    if(n[2]>0.7){c.ground=t.world;                 // a groundentity that doesn't move: the world
      if(Math.hypot(c.vel[0],c.vel[1],c.vel[2])<40){c.vel=[0,0,0];c.avel=[0,0,0];}}
  }
}
// explodechunk's start: shown, the throw (phyvel) and the spin
function expThrow(c){
  const tg=gameKey(c.ei,'target'),t=tg?gameTn(tg)[0]:null,to=t!=null&&ENTS[t]?(ENTS[t].origin||(ENTS[t].box&&ENTS[t].box.origin)):null;
  if(!to){c.st='dead';return;}                    // no target: the script stops on its error, the chunk stays
  const o=c.o,v=[o[0]-to[0],o[1]-to[1],o[2]-to[2]],len=Math.hypot(v[0],v[1],v[2]);
  const n=len>0?[v[0]/len,v[1]/len,v[2]/len]:[0,0,0],sc=-len;
  c.vec=[n[0]*sc,n[1]*sc,n[2]*sc*1.5];
  for(let k=0;k<3;k++)c.vel[k]+=c.vec[k];         // physics_velocity, still a mover
  let ax=rnd(len/3)*(rndi(3)-1),ay=rnd(len/3)*(rndi(3)-1),az=rnd(len/3)*(rndi(3)-1);
  const xnum=Math.abs(o[0]-to[0]),ynum=Math.abs(o[1]-to[1]);
  if(xnum>ynum)ax=o[0]>to[0]?len*-0.5-rnd(0.5):len*0.5+rnd(0.5);
  else az=o[1]>to[1]?len*0.5+rnd(0.5):len*-0.5-rnd(0.5);
  c.avel=[ax,ay,az];c.spin=[ax,ay,az];
  c.st='push';
}
// One server frame of a running set: the movers and bouncers move (physics), then the
// script's threads whose wait is over run.
function expFrame(R){
  const k=R.k,dt=EXP_FRAME/1000;let vis=false;
  for(const c of R.chunks){
    if(c.st==='push'){for(let j=0;j<3;j++){c.o[j]+=c.vel[j]*dt;c.ang[j]+=c.avel[j]*dt;}}
    else if(c.st==='phys')expToss(c);
  }
  for(const x of R.exps)if(!x.done&&k>=x.at){x.done=true;EXP.hid.add(x.ei);EXP.solid=null;vis=true;}
  for(const s of R.sm)if(!s.on&&k>=s.at){s.on=true;EXP.solid=null;}
  for(const c of R.chunks){
    if(c.st==='wait'&&k>=c.at){c.ks=k;expThrow(c);continue;}
    if(c.st==='dead'||c.st==='wait'||c.st==='gone')continue;
    if(c.touched&&k>c.tk)expSink(c);
    const r=k-c.ks;
    if(r===4){c.st='phys';c.vel=[c.vec[0],c.vec[1],c.vec[2]+1];}    // physics_on 1: velocity (0 0 1), then physics_velocity again
    if(r===10){c.inc=10+rndi(15);c.dec=c.spin.map(v=>v/c.inc);c.cur=c.spin.slice();}
    if(c.dec&&r>=10&&r<10+c.inc){for(let j=0;j<3;j++)c.cur[j]-=c.dec[j];c.avel=c.cur.slice();}
    if(c.dec&&r===10+c.inc+200){c.st='gone';EXP.hid.add(c.ei);vis=true;}   // wait 10, then deleted
  }
  for(const c of R.chunks)if(c.touched&&c.tk==null)c.tk=k;
  R.k++;
  if(R.chunks.every(c=>c.st==='gone'||c.st==='dead')&&R.exps.every(x=>x.done)&&R.sm.every(s=>s.on))R.done=true;
  return vis;
}
function expXf(c){
  const ax=anglesAxis(c.ang),o=c.o0;
  return{R:[ax[0][0],ax[1][0],ax[2][0],ax[0][1],ax[1][1],ax[2][1],ax[0][2],ax[1][2],ax[2][2]],o:o,t:[c.o[0]-o[0],c.o[1]-o[1],c.o[2]-o[2]],ang:c.ang.slice()};
}
function expPose(c,home){
  if(home){EXP.mov.delete(c.ei);entPose(c.d,null);return;}
  const X=expXf(c);let m=EXP.mov.get(c.ei);if(!m){m={d:c.d,xf:X};EXP.mov.set(c.ei,m);}else m.xf=X;
  entPose(c.d,X);
}
// the brush entity that moves (a door or a flying chunk), for its box
function movObj(ei){const m=EXP.mov.get(ei);if(m)return m.d;return DOORS&&DOORS.get(ei)||null;}
// Run the running sets up to now (ms), a server frame at a time (at most 10 s at once);
// true when anything changed.
function expAdvance(now){
  let changed=false,vis=false;
  for(const R of [...EXP.busy]){
    let due=Math.floor((now-R.t0)/EXP_FRAME)-R.k;if(due<=0)continue;
    if(due>200){R.t0+=(due-200)*EXP_FRAME;due=200;}
    for(let i=0;i<due&&!R.done;i++)if(expFrame(R))vis=true;
    for(const c of R.chunks)if(c.st==='push'||c.st==='phys'||(c.st==='gone'&&!c.parked)){expPose(c,false);if(c.st==='gone')c.parked=true;}
    changed=true;
    if(R.done)EXP.busy.delete(R);
  }
  if(vis){rebuildWorld();updateSelPanel();}
  return changed;
}
// ---- the Selection buttons -----------------------------------------------------------------
function expBtnRender(){
  const run=$('bExpRun'),rs=$('bExpReset');if(!run)return;
  const sets=expSelSets();
  if(!sets.size){run.style.display=rs.style.display='none';return;}
  run.style.display=rs.style.display='';
  const L=[...sets].sort((a,b)=>a-b),fresh=L.filter(s=>!EXP.runs.has(s)),ran=L.filter(s=>EXP.runs.has(s));
  run.disabled=!fresh.length;rs.disabled=!ran.length;
  const nm=l=>'#set '+l.join(', ');
  run.title=fresh.length?'Set off exploder '+nm(fresh)+' as global/exploder.scr\'s "explode" does: its $exploder goes, its chunks are thrown toward their targets and land, then vanish (no sounds or emitters). Reset exploder puts it back':
    'Exploder '+nm(L)+' has gone off: Reset exploder puts it back to set it off again';
  rs.title=ran.length?'Put exploder '+nm(ran)+' back as the level starts: its $exploder and chunks where the .map has them and shown (a chunk you hid too)':'Exploder '+nm(L)+' hasn\'t gone off';
}
function expRunSel(){
  const sets=[...expSelSets()].filter(s=>!EXP.runs.has(s));
  if(!sets.length){flash(expSelSets().size?'This exploder has gone off: Reset exploder first':'Select an exploder, explodersmashed, exploderchunk or exploderfire first');return;}
  const now=performance.now();for(const s of sets)expRun(s,now);
  const n=sets.reduce((a,s)=>a+EXP.sets.get(s).chunk.length,0);
  flash('Exploder #set '+sets.join(', ')+' set off'+(n?': '+n+' chunk'+(n>1?'s':'')+' thrown':''));
  expBtnRender();requestDraw();
}
function expReset(sets){
  sets=sets||[...expSelSets()].filter(s=>EXP.runs.has(s));if(!sets.length)return;
  for(const s of sets){const R=EXP.runs.get(s);if(!R)continue;
    EXP.busy.delete(R);EXP.runs.delete(s);
    for(const x of R.exps)EXP.hid.delete(x.ei);
    for(const c of R.chunks){EXP.hid.delete(c.ei);hidEnt.delete(c.ei);if(EXP.mov.has(c.ei)||c.st!=='wait')expPose(c,true);}
    const S=EXP.sets.get(s);if(S)for(const ei of S.chunk){hidEnt.delete(ei);EXP.hid.delete(ei);}}
  EXP.solid=null;rebuildWorld();selectionChanged();
  flash('Exploder #set '+sets.join(', ')+' put back');
}
// the Exploder part of an info card
function expInfo(ei){
  const r=expRole(ei);if(!r||!EXP.sets)return '';
  const set=expKey(ei,'set');
  if(set==null)return '<h4>Exploder</h4><div class="note warn">No "#set": global/exploder.scr stops with an error for it.</div>';
  const S=EXP.sets.get(set),p=expKey(ei,'pause'),rows=[];
  rows.push(['#set',esc(String(set))+' · '+[['exploder','exploders'],['smashed','smashed'],['chunk','chunks'],['fire','fires'],['trigger','triggers']].map(([k,pl],i)=>S[['exploder','smashed','chunk','fire','trigger'][i]].length+' '+(S[['exploder','smashed','chunk','fire','trigger'][i]].length===1?k:pl)).join(', ')]);
  const what={exploder:'hides and goes notsolid',smashed:'shows and goes solid (drawn here all the time)',chunk:'is thrown toward its target, lands, and 10 s after it stops spinning is deleted',
    fire:'plays its emitter (not shown here)',trigger:'sets the exploder off when triggered'}[r];
  rows.push(['when it goes off',esc('it '+what+(r!=='trigger'?(p>0?', after "#pause" '+p+' s':', at once'):''))]);
  if(r==='chunk'){const tg=gameKey(ei,'target'),t=tg?gameTn(tg)[0]:null;
    rows.push(['thrown toward',t!=null?linkEnt(t):'<span class="warn">no target: the script stops with an error</span>']);}
  const run=EXP.runs.get(set);
  rows.push(['now',esc(run?(run.done?'gone off':'going off'):'as the level starts')]);
  return '<h4>Exploder</h4>'+kvTable(rows)+'<div class="note">Run exploder (Selection) sets off its #set as global/exploder.scr does, without sounds or emitters; Reset exploder puts it back. "#pause" is read as a whole number of seconds (atoi), as the game reads a "#" key.</div>';
}

// ============================================================================
//  Game cvars: what the game draws for them
// ============================================================================
// Each frame the cvars that are set put their lines in DL, drawn the way the game draws
// its debug lines (R_DrawDebugLines: one pixel wide, not blended, hidden behind walls).
// The game measures most of them from the player: here the camera is a standing
// player's eye and the player's feet are 82 units under it (DEFAULT_VIEWHEIGHT).
const VIEWHEIGHT=82;
function feetPos(){return[cam.pos[0],cam.pos[1],cam.pos[2]-VIEWHEIGHT];}
function dist2(a,b){const x=a[0]-b[0],y=a[1]-b[1],z=a[2]-b[2];return x*x+y*y+z*z;}
let DL=[];                                     // this frame's lines: end, other end, colour (as B.gvX)
function dl(p,q,c){DL.push(p[0],p[1],p[2],q[0],q[1],q[2],c[0],c[1],c[2],1,q[0],q[1],q[2],p[0],p[1],p[2],c[0],c[1],c[2],1);}
const DC={blue:[0,0,1],yellow:[1,1,0],cyan:[0,1,1],magenta:[1,0,1],red:[1,0,0],green:[0,1,0],white:[1,1,1]};
// G_DebugBBox / G_DebugRotatedBBox: corner i takes x from mins with bit 1 set, y with bit
// 2, z with bit 4 (else maxs); the top and bottom loops in the colour, the uprights blue
function dlBox8(P,c){
  for(const[a,b]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4]])dl(P[a],P[b],c);
  for(let i=0;i<4;i++)dl(P[i],P[i+4],DC.blue);}
function boxPts(o,mn,mx,ax){const P=[];
  for(let i=0;i<8;i++){const t=[(i&1)?mn[0]:mx[0],(i&2)?mn[1]:mx[1],(i&4)?mn[2]:mx[2]];
    P.push(ax?[o[0]+t[0]*ax[0][0]+t[1]*ax[1][0]+t[2]*ax[2][0],o[1]+t[0]*ax[0][1]+t[1]*ax[1][1]+t[2]*ax[2][1],
               o[2]+t[0]*ax[0][2]+t[1]*ax[1][2]+t[2]*ax[2][2]]:[o[0]+t[0],o[1]+t[1],o[2]+t[2]]);}
  return P;}
// G_DebugCircle: 24 segments in the plane of the view's up and right, or flat; only
// within 1000 units of the player, plus the radius
function dlCircle(org,r,c,horiz,feet){
  if(dist2(feet,org)>(1000+r)*(1000+r))return;
  let F,L;
  if(horiz){F=[1,0,0];L=[0,-1,0];}
  else{const a=camAxes();F=a.u;L=a.r;}         // AngleVectors(NULL, &left, &forward): right and up
  let prev=null;
  for(let i=0;i<=24;i++){const t=i*15*Math.PI/180,s=Math.sin(t)*r,k=Math.cos(t)*r;
    const p=[org[0]+s*F[0]-k*L[0],org[1]+s*F[1]-k*L[1],org[2]+s*F[2]-k*L[2]];
    if(prev)dl(prev,p,c);prev=p;}}
// G_DrawDebugNumber: digits of up to 8 strokes, 8 x 8 units times scale and 10 apart,
// facing the view and centred on org; only within 1000 units of the player
const LED_NUM=[[1,3,4,5,6,7],[4,5],[1,4,2,7,3],[1,4,2,5,3],[6,4,2,5],[1,6,2,5,3],[1,6,2,5,7,3],[1,8],[1,2,3,4,5,6,7],[1,6,4,2,5,3],[9,10,11,12],[2]];
const LED_SEG=[null,[-4,8,4,8],[-4,4,4,4],[-4,0,4,0],[4,8,4,4],[4,4,4,0],[-4,8,-4,4],[-4,4,-4,0],[4,8,-4,0],[-1,2,1,2],[1,2,1,0],[-1,0,1,0],[-1,0,-1,2]];
function dlNumber(org,num,scale,c,feet){
  if(dist2(feet,org)>1000*1000)return;
  const a=camAxes(),up=[a.u[0]*scale,a.u[1]*scale,a.u[2]*scale],lf=[-a.r[0]*scale,-a.r[1]*scale,-a.r[2]*scale];
  const txt=String(Math.trunc(num));
  let s=[org[0]+(txt.length-1)*5*lf[0],org[1]+(txt.length-1)*5*lf[1],org[2]+(txt.length-1)*5*lf[2]];
  for(const ch of txt){const n=ch==='.'?10:ch==='-'?11:ch.charCodeAt(0)-48;
    if(n>=0&&n<12)for(const l of LED_NUM[n]){const L=LED_SEG[l];
      dl([s[0]-L[0]*lf[0]+L[1]*up[0],s[1]-L[0]*lf[1]+L[1]*up[1],s[2]-L[0]*lf[2]+L[1]*up[2]],
         [s[0]-L[2]*lf[0]+L[3]*up[0],s[1]-L[2]*lf[1]+L[3]*up[1],s[2]-L[2]*lf[2]+L[3]*up[2]],c);}
    s=[s[0]-10*lf[0],s[1]-10*lf[1],s[2]-10*lf[2]];}}

// ---- what each map entity is in game -------------------------------------------------------
// The class a map entity spawns as (SpawnArgs::getClassDef): the game's class of that
// classname (OpenMoHAA's CLASS_DECLARATIONs in code/fgame, by id and by C++ name), else the
// class the "classname" line of its .tik's init block names, else Object (an Animate).
// Grouped by what the cvars need of them: their ShowInfo (g_entinfo), whether they take an
// entity number (simple entities and listeners don't), whether they are solid.
const GAME_CLASS={};
for(const[g,names]of Object.entries({
  door:'door func_door func_rotatingdoor normaldoor rotatingdoor script_door scriptdoor slidingdoor',
  actor:'actor',
  turret:'portableturret turretgun vehicleturretgun vehicleturretguntandem',
  weapon:'carryableturret inventoryitem weapon',
  item:'ammoentity armor dynitem health health_020 item',
  vehicle:'drivablevehicle drivablevehicletandem fixedturret script_drivablevehicle script_vehicle vehicle vehiclehalftrack vehicletank vehicletanktandem vehiclewheelsx2 vehiclewheelsx4',
  slave:'fulcrum func_beam func_fulcrum func_randomspawn func_respawn func_sinkobject func_spawn func_spawnchain func_spawnoutofsight funcbeam randomspawn respawn script_aimedstrafinggunfire script_model script_model_realdamage script_object script_origin script_simplestrafinggunfire script_skyorigin scriptaimedstrafinggunfire scriptmodel scriptmodelrealdamage scriptorigin scriptsimplestrafinggunfire scriptskyorigin scriptslave sinkobject spawn spawnchain spawnoutofsight',
  trigger:'explodeobject exploder explodingwall func_explodeobject func_exploder func_explodingwall func_multi_exploder func_viewjitter gib mover multiexploder play_sound_triggered randomspeaker sound_randomspeaker sound_speaker teleporter touchfield trigger trigger_box trigger_camerause trigger_changelevel trigger_clickitem trigger_damagetargets trigger_entity trigger_exit trigger_givepowerup trigger_hurt trigger_landmine trigger_multiple trigger_multipleall trigger_music trigger_nodamage trigger_once trigger_push trigger_pushany trigger_pushobject trigger_relay trigger_save trigger_secret trigger_sideduse trigger_teleport trigger_use trigger_useonce trigger_vehicle triggerall triggerbox triggerbypushobject triggercamerause triggerchangelevel triggerclickitem triggerdamagetargets triggerentity triggerexit triggergivepowerup triggerhurt triggerlandmine triggermusic triggernodamage triggeronce triggerplaysound triggerpush triggerpushany triggerrelay triggerreverb triggersave triggersecret triggersideduse triggerspeaker triggeruse triggeruseonce triggervehicle viewjitter',
  camera:'camera func_camera info_player_intermission playerintermission',
  spline:'info_splinepath splinepath',
  animate:'animate body damagemodel effectentity explosion func_throwobject func_useobject interactobject lodslave object plant_puffdaddy player projectile projectilegenerator projectilegenerator_gun projectilegenerator_heavy projectilegenerator_projectile puffdaddy sentient simpleactor smokegrenade throbbingbox_explodeflak88 throbbingbox_explodenebelwerfer throbbingbox_explodeplayerflak88 throbbingbox_explodeplayernebelwerfer throbbingbox_explosive throbbingbox_stickybomb throwobject tossobject useobject vehiclebase viewmaster viewthing',
  entity:'barrelobject crateobject decal emitter entity fallingrock fencepost func_barrel func_crate func_emitter func_fallingrock func_fencepost func_horizontalpipe func_ladder func_monkeybars func_objective func_pushobject func_rain func_remove func_runthrough func_teleportdest func_touchanim func_towobjective func_useanim func_useanimdest func_window funcladder funcremove gravpathnode helmetobject horizontalpipe info_grav_pathnode info_notnull infonotnull light misc_model miscmodel monkeybars objective portal_camera portal_surface portalcamera portalsurface projectilegenerator_target projectiletarget pushobject rain runthrough teleporterdestination touchanim towobjective useanim useanimdestination vehiclecollisionentity vehiclesoundentity windowobject world worldspawn',
  simple:'aispawnpoint attractivenode grenadehint info_aispawnpoint info_grenadehint info_pathnode info_player_allied info_player_axis info_player_deathmatch info_player_start info_vehiclepoint info_waypoint pathnode playerallieddeathmatchstart playeraxisdeathmatchstart playerdeathmatchstart playerstart simplearchivedentity simpleentity tempwaypoint testplayerstart vehiclepoint waypoint',
  listener:'ammo animationevent botcontroller cameramanager clientgamecommandmanager clientspecialeffectsmanager consoleevent consolehider consoleview dm_manager dm_team dmconsolehider emitterloader event fsfile game gravpath gravpathmanager hud info_landmark info_null infolandmark infonull level lightstyleclass listener lodmaster navmaster osfile parm pathsearch scriptevent scriptmaster scriptthread scripttimer soundmanager spawnargs statsupdater targetlist uifakklabel view3d voteupload'}))
  for(const n of names.split(' '))GAME_CLASS[n]=g;
// solid as they set themselves up (a script can change it): brush entities but the ones
// that only trigger, the AI, vehicles, script objects with a model, and these
const SOLID_CLASSES=new Set(['interactobject','damagemodel','useobject','func_useobject','throbbingbox_stickybomb']);
const NONSOLID_BRUSH=new Set(['func_rain','func_runthrough','func_touchanim','func_useanim','func_emitter','func_remove','func_teleportdest','func_useanimdest']);
// Level::inhibitEntity: what the spawnflags keep out of this game (8 SPAWNFLAG_DETAIL only
// with detail 0, which isn't the default)
function inhibitEntity(sf,map){
  if(CVARS.g_gametype!==0)return !!(sf&0x800);                 // NOT_DEATHMATCH
  if(!CVARS.developer&&(sf&0x2000))return true;                 // DEVELOPMENT
  if(map==='t3l2')return !!(sf&0x100);
  switch(CVARS.skill){case 0:return !!(sf&0x100);case 1:return !!(sf&0x200);case 2:case 3:return !!(sf&0x400);}
  return false;
}
// Level::SpawnEntities: the world is 1022 (ENTITYNUM_WORLD), the players come first, then
// each map entity in turn takes the next number from sv_maxclients up; radnum counts every
// object spawned, from 1. What the cvars that set this are now is part of the key.
let GAMEENTS=null;
// ---- the level script: what it spawns and sets (D.scr, LevelScript in mohaa_map_view.py) ----
// The viewer doesn't run the script: the build reads its spawn lines and the lines that
// give the same entity its origin, angles, targetname, target, model... (through
// local.x / level.x = spawn, or its $targetname). The entities it could place are added
// after the map's own (MAP.nMap is where the map's end), so they are drawn, labelled,
// linked (a waypoint's "target"), found and selected like the map's. They have no entity
// number here (the game gives one when the script runs) and aren't in the .pth.
function scriptEnts(){
  MAP.nMap=MAP.ents.length;
  const S=D.scr;if(!S||!S.ents)return;
  // the build numbered their models from the map's entity count; if the page reads
  // another count, those numbers point elsewhere
  if(S.base!==MAP.nMap&&D.modelOf)for(const k of Object.keys(D.modelOf))if(+k>=S.base)delete D.modelOf[k];
  for(const r of S.ents){
    const e={kv:r.kv.map(x=>[x[0],x[1]]),kvl:{},brushes:[],patches:[],terrains:[],prims:[],ts:-1,te:-1,scr:r};
    for(const[k,v]of e.kv){const kl=k.toLowerCase();if(!(kl in e.kvl))e.kvl[kl]=v;}
    e.cls=(e.kvl.classname||'').toLowerCase();
    MAP.ents.push(e);}
  // the map's own entities whose target the script sets (a map node joined to its own)
  for(const m of S.mods||[]){const e=MAP.ents[m[0]];if(!e||m[0]>=MAP.nMap)continue;
    e.kv=e.kv.filter(kv=>!/^[$#]?target$/i.test(kv[0]));e.kv.push([m[1],m[2]]);e.kvl[m[1]]=m[2];
    (e.scrMods=e.scrMods||[]).push(m);}
}
// placed script entities the game gives an entity number to (not simple ones such as
// waypoints), as entityKinds counts the map's
function scrReal(){const ek=D.ek||{},simple=new Set([...(ek.simple||[]),...(ek.dropped||[])]);let n=0;
  for(let ei=MAP.nMap;ei<MAP.ents.length;ei++)if(!simple.has(MAP.ents[ei].cls))n++;return n;}
function scrWhere(f,l){const F=(D.scr.files||[])[f];return (F?F[0]:'?')+' line '+l;}
function scrSummary(){const S=D.scr,n=S.ents.length,u=S.nun|0;
  return n+' entit'+(n===1?'y':'ies')+' placed, '+scrReal()+' real placed, '+u+' not, '+S.cvars.length+' setcvar';}
function scrEntHtml(e){
  const r=e.scr;let lines=['// '+scrWhere(r.f,r.l),r.s];
  for(const x of r.x||[])lines.push('// line '+x[1]+(x[0]!==r.f?' of '+((D.scr.files[x[0]]||['?'])[0]):''),x[2]);
  let h='<h4>Level script<span class="sp"></span>'+copyBtn(lines.join('\n'),'Copy')+'</h4><pre>'+esc(lines.join('\n'))+'</pre>';
  h+='<div class="note">Spawned while the game runs. The viewer doesn\'t run the script: it puts the entity where these lines say.</div>';
  if(r.u){const u=Object.entries(r.u);if(u.length)h+='<div class="note warn">Not followed (worked out while the game runs): '+u.map(([k,v])=>esc(k)+' from <code>'+esc(v)+'</code>').join('; ')+'</div>';}
  return h;
}
// Open a file of the level script (the map's own .scr is 0) in the launcher's Text Editor:
// a file on disk as it is, one in a pak extracted first. In a browser, its path is copied.
function openScr(i){
  const F=D.scr&&D.scr.files&&D.scr.files[i];if(!F)return;
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-open-scr\n'+F[0]+'\n'+F[1]);
    flash('Opening '+F[0]+' in your Text Editor');return;}}catch(_e){}
  copyText(F[1],'Opening a file works from the launcher: the path of '+F[0]+' was copied');
}
function scrCard(){
  infoMode='scr';
  const S=D.scr;if(!S){card('Level script','<div class="note">This map has no level script.</div>');return;}
  let h='<div class="note">What the map\'s .scr spawns and sets, read from its lines (the script isn\'t run). Spawned entities are placed where the lines that follow give their origin; one whose origin comes from something only the game knows (a thread\'s parameter, a loop, another entity moved by script) is listed below, not drawn. Show > Script ents (Ctrl+E) shows or hides them.</div>';
  h+='<h4>Files</h4>'+kvTable(S.files.map((F,i)=>[i?'runs':'map',esc(F[0])+' <button class="sm" data-openscr="'+i+'" title="Open it in your Text Editor (from the launcher)">Open</button> <span class="co">'+esc(F[1])+'</span>']));
  if(S.miss&&S.miss.length)h+='<div class="note warn">Run by the script but not found: '+S.miss.map(esc).join(', ')+'</div>';
  // the placed entities, by class
  const placed=[];for(let ei=MAP.nMap;ei<MAP.ents.length;ei++)placed.push(ei);
  h+='<h4>Spawned and placed ('+placed.length+')</h4>';
  if(placed.length){
    const by=new Map();for(const ei of placed){const c=MAP.ents[ei].kvl.classname||'?';if(!by.has(c))by.set(c,[]);by.get(c).push(ei);}
    for(const[c,l]of[...by.entries()].sort((a,b)=>a[0].localeCompare(b[0]))){
      h+='<div><b>'+esc(c)+'</b> <span class="co">'+l.length+'</span></div>';
      h+=kvTable(l.slice(0,300).map(ei=>{const e=MAP.ents[ei];return[String(e.scr.l),linkEnt(ei)+' '+esc(e.kvl.origin?fvec(parseVec(e.kvl.origin,3)||[0,0,0]):'')+(e.kvl.target?' → $'+esc(e.kvl.target):'')];}));
      if(l.length>300)h+='<div class="note">… and '+(l.length-300)+' more</div>';}
  }else h+='<div class="note">None: every spawn line takes its place from something only the game knows.</div>';
  if(S.nun){h+='<h4>Spawned, not placed ('+S.nun+')</h4>';
    h+=kvTable(S.un.map(r=>[esc(scrWhere(r.f,r.l)),'<code>'+esc(r.s)+'</code><div class="note">'+esc(r.why)+'</div>']));
    if(S.nun>S.un.length)h+='<div class="note">… and '+(S.nun-S.un.length)+' more</div>';}
  if((S.mods||[]).length){h+='<h4>The map\'s entities it joins ('+S.mods.length+')</h4>';
    h+=kvTable(S.mods.slice(0,300).map(m=>[esc(scrWhere(m[3],m[4])),linkEnt(m[0])+' → $'+esc(m[2])]));}
  h+='<h4>setcvar ('+S.cvars.length+')<span class="sp"></span>'+(S.cvars.length?copyBtn(S.cvars.map(c=>'setcvar "'+c[0]+'" "'+(c[1]==null?'':c[1])+'"').join('\n'),'Copy'):'')+'</h4>';
  h+=S.cvars.length?kvTable(S.cvars.map(c=>[esc(c[0]),(c[1]==null?'<span class="warn">worked out while the game runs</span>':'"'+esc(c[1])+'"')+' <span class="co">'+esc(scrWhere(c[2],c[3]))+'</span>'])):'<div class="note">none</div>';
  if(S.world.length){h+='<h4>$world lines ('+S.world.length+')</h4>'+kvTable(S.world.map(w=>[esc(scrWhere(w[1],w[2])),'<code>'+esc(w[0])+'</code>']));
    h+='<div class="note">The worldspawn settings the script changes as it runs (farplane, farplane_color...). The view keeps the map\'s own; r_farplane in the game cvars (`) tries a distance out.</div>';}
  card('Level script',h);
}
function gameEnts(){
  const key=[CVARS.g_gametype,CVARS.skill,CVARS.developer,CVARS.sv_maxclients].join(':');
  if(GAMEENTS&&GAMEENTS.key===key)return GAMEENTS.e;
  const map=String(D.path||'').replace(/^.*[\\/]/,'').replace(/\.(bsp|map)$/i,'').toLowerCase();
  const out=[];let num=CVARS.sv_maxclients,rad=0,n=0;
  for(let ei=0;ei<MAP.ents.length;ei++){
    const e=MAP.ents[ei],k=e.kvl,c=e.cls,R={g:'',num:-1,rad:0,gone:false,cn:'',why:''};out.push(R);
    if(ei===0){R.g='entity';R.num=1022;continue;}
    if(e.scr){R.g='script';R.why='spawned by the level script while the game runs: it gets its entity number then';continue;}
    if(isStaticProp(ei)){R.g='static';R.why='a static model: scenery the map compiler made, not an entity'+
      (D.bsp&&D.bsp.firstStatic>0?' (not in the .bsp\'s entity lump, so it can\'t be modified here)':'');continue;}
    if(WORLDLIKE[c]){R.g='none';R.why='its brushes become part of the world when the map is compiled';continue;}
    if(k.spawnflags!=null&&c!=='info_pathnode'&&c!=='info_patharea'&&inhibitEntity(parseInt(k.spawnflags,10)|0,map)){
      R.g='inhibited';R.why='its spawnflags keep it out of this game (g_gametype, skill, developer)';continue;}
    if(c==='light'){R.g='none';R.why='lights are only for the map compiler: the game never spawns them';continue;}
    let g=GAME_CLASS[c];
    if(!g){
      const mi=ENTS[ei].model,M=mi>=0?D.models[mi]:null,cn=M&&M.cn?String(M.cn).toLowerCase():'';
      if(M&&parseInt(k.make_static||'0',10)){R.g='none';R.why='"make_static": it is drawn as scenery, not spawned';continue;}
      R.cn=cn;
      if(cn){g=GAME_CLASS[cn];if(!g){R.g='none';R.why='its .tik names class '+M.cn+', which the game doesn\'t have';continue;}}
      else g='animate';                          // Object
    }
    rad++;R.g=g;R.rad=rad;
    if(g==='simple'){R.why='a simple entity (no entity number)';continue;}
    if(g==='listener'){R.why='not an entity in game';continue;}
    R.num=num++;n++;
    if(c==='misc_model'||c==='func_remove'){R.gone=true;R.why='it removes itself once it has spawned';}
  }
  GAMEENTS={key:key,e:out,count:n};
  return out;
}
// The entity's box and angles at the level's start: a brush model's bounds (a door where
// it is now); for a model the "setsize" key, else its .tik's setsize, else its .tik's
// bounds times "scale" (Entity::setModel); a point entity has no size. An AI (class
// Actor) replaces all that with a standing player's box as it starts (Actor::EventStart:
// setSize(MINS, MAXS), its start coming after its spawn args).
function gameBox(ei){
  const e=MAP.ents[ei],X=ENTS[ei],b=X.box,k=e.kvl;
  if(X.hasGeo&&b){const d=DOORS&&DOORS.get(ei)||null,m=movObj(ei);return{o:b.origin,mins:b.mins,maxs:b.maxs,ang:[0,0,0],door:d,mv:m,dx:m?doorXf(ei):null};}
  const o=X.origin;if(!o)return null;
  const ang=entAngles(k),ss=parseVec(k.setsize,6);
  if(gameEnts()[ei].g==='actor')return{o:o,mins:[-15,-15,0],maxs:[15,15,94],ang:ang};
  if(ss)return{o:o,mins:ss.slice(0,3),maxs:ss.slice(3),ang:ang};
  if(X.model>=0){const M=D.models[X.model],sc=parseFloat(k.scale)||1;
    if(M.ss)return{o:o,mins:M.ss[0],maxs:M.ss[1],ang:ang};
    const tb=M.tb||[[-4,-4,-4],[4,4,4]];
    return{o:o,mins:tb[0].map(v=>v*sc),maxs:tb[1].map(v=>v*sc),ang:ang};}
  return{o:o,mins:[0,0,0],maxs:[0,0,0],ang:ang};
}
// A key as the game reads it ("$name" and "#name" included: spawnKeys).
function gameKey(ei,name){return MAP.ents[ei].kvl[name]||'';}
let GAME_TN=null;
// the entities of a targetname, in spawn order (G_FindTarget takes the first)
function gameTn(name){
  if(!GAME_TN){GAME_TN=new Map();MAP.ents.forEach((e,ei)=>{const t=gameKey(ei,'targetname');
    if(t){let l=GAME_TN.get(t);if(!l){l=[];GAME_TN.set(t,l);}l.push(ei);}});}
  return GAME_TN.get(name)||[];}
// its corners in G_DebugRotatedBBox's order (doorCorners numbers them the other way round)
function gameBoxPts(B){
  if(B.mv&&B.dx){const C=doorCorners(B.mv,B.dx);return C.map((_,i)=>C[i^7]);}
  return boxPts(B.o,B.mins,B.maxs,anglesAxis(B.ang));}
function gameOrigin(B){return B.dx?xfP(B.dx,B.o):B.o;}
function entSolid(ei){
  const R=gameEnts()[ei],e=MAP.ents[ei],X=ENTS[ei];
  if(R.num<0||R.gone||ei===0)return false;
  switch(R.g){
    case 'door':case 'actor':case 'vehicle':return true;
    case 'slave':                                // SetModelEvent: a brush model BSP, a .tik a box; NOT_SOLID (1)
      return (X.hasGeo||X.model>=0)&&!((parseInt(e.kvl.spawnflags||'0',10)|0)&1);
    case 'entity':return X.hasGeo&&!NONSOLID_BRUSH.has(e.cls);
    case 'animate':return SOLID_CLASSES.has(e.cls)||SOLID_CLASSES.has(R.cn);
  }
  return false;
}
// sent to the client (g_entinfo shows only those): it has something to draw, isn't of a
// class kept from clients (triggers, func_ladder), and the server sends it from here
function entSent(ei){
  const R=gameEnts()[ei],X=ENTS[ei],c=MAP.ents[ei].cls;
  if(R.num<0||R.gone||ei===0)return false;
  if(!X.hasGeo&&X.model<0)return false;
  if(R.g==='trigger'||c==='func_ladder')return false;
  return GV?gvSent(GV,ei):true;
}

// ---- sv_showentnums, sv_showbboxes, g_entinfo --------------------------------------------
// The numbers: yellow, twice the size, at the origin raised by the box's top (the world's
// 1022 sits at the map's origin: it has no size)
function dlEntNums(feet){
  const G=gameEnts();
  dlNumber([0,0,0],1022,2,DC.yellow,feet);
  for(let ei=1;ei<MAP.ents.length;ei++){const R=G[ei];if(R.num<0||R.gone)continue;
    const B=gameBox(ei);if(!B)continue;
    const o=gameOrigin(B);dlNumber([o[0],o[1],o[2]+B.maxs[2]],R.num,2,DC.yellow,feet);}}
// Entity::DrawBoundingBox for every entity whose centre is within 1000 of the player
function dlBoxes(m,feet){
  const G=gameEnts();
  if(m>=100||m<0)return;                         // 100+: g_monitor's entity; negative: the player's
  for(let ei=1;ei<MAP.ents.length;ei++){const R=G[ei];if(R.num<0||R.gone)continue;
    const B=gameBox(ei);if(!B)continue;
    const P=gameBoxPts(B),bb=ptsBounds(P),cen=[(bb.mins[0]+bb.maxs[0])/2,(bb.mins[1]+bb.maxs[1])/2,(bb.mins[2]+bb.maxs[2])/2];
    if(dist2(cen,feet)>1000*1000)continue;
    const tik=ENTS[ei].model>=0,solid=entSolid(ei);
    if(m===1){if(solid)dlBox8(P,DC.yellow);}
    else if(m===2){if(solid)dlBox8(boxPts([0,0,0],[bb.mins[0]-1,bb.mins[1]-1,bb.mins[2]-1],[bb.maxs[0]+1,bb.maxs[1]+1,bb.maxs[2]+1],null),DC.magenta);}
    else if(m===3){if(tik)dlBox8(P,DC.yellow);}
    else if(m===4)dlBox8(P,DC.yellow);
    else if(m===7){if(tik){const M=D.models[ENTS[ei].model],sc=parseFloat(MAP.ents[ei].kvl.scale)||1,tb=M.tb||[[-4,-4,-4],[4,4,4]];
      dlBox8(boxPts(B.o,tb[0].map(v=>v*sc),tb[1].map(v=>v*sc),anglesAxis(B.ang)),DC.cyan);}}
    else if(m===8){if(tik){dlBox8(P,DC.yellow);dlBox8(boxPts(B.o,[-4,-4,-4],[4,4,4],null),DC.cyan);}}
    // 9 to 28: a sentient's hit spheres (the Model Viewer draws them), anything else solid
    // its plain box
    if(m>=9&&m<=28&&solid&&R.g!=='actor')dlBox8(boxPts(gameOrigin(B),B.mins,B.maxs,null),DC.yellow);
  }}
// Actor::ShowInfo's numbers: the map's keys, the game's defaults, then FixAIParameters
// (every think): mindist down to the leash, maxdist at least mindist + 128, and with a
// farplane no further than 82.8% of it
function actorRadii(ei){
  const k=MAP.ents[ei].kvl,wk=MAP.ents[0]?MAP.ents[0].kvl:{},num=(v,d)=>{const f=parseFloat(v);return isFinite(f)?f:d;};
  const r={leash:num(k.leash,512),mind:num(k.mindist,128),maxd:num(k.maxdist,1024),hear:num(k.hearing,2048),
           sight:num(k.sight,num(wk.ai_visiondistance,2048)),health:num(k.health,100)};
  if(r.mind<0)r.mind=0;if(r.maxd<256)r.maxd=256;
  if(r.leash<r.mind)r.mind=r.leash;
  if(r.maxd<r.mind+127)r.maxd=r.mind+128;
  const far=parseFloat(wk.farplane)||0;
  if(far>0&&r.maxd>far*0.828){r.maxd=far*0.828;if(r.maxd<r.mind+127)r.mind=Math.max(0,r.maxd-128);}
  return r;
}
let ENTTEXT=[];                                  // g_entinfo's strings: {p: bottom left, s: text}
// ShowInfo of everything sent: what each class shows when the player looks at it
function dlEntInfo(v,feet){
  const G=gameEnts(),eye=cam.pos,f=camAxes().f,maxd=CVARS.g_entinfo_max;
  for(let ei=1;ei<MAP.ents.length;ei++){
    const R=G[ei];if(R.num<0||R.gone||!entSent(ei))continue;
    const B=gameBox(ei);if(!B)continue;
    const k=MAP.ents[ei].kvl,o=gameOrigin(B);
    const cen=[o[0]+(B.mins[0]+B.maxs[0])/2,o[1]+(B.mins[1]+B.maxs[1])/2,o[2]+(B.mins[2]+B.maxs[2])/2];
    const d=[cen[0]-eye[0],cen[1]-eye[1],cen[2]-eye[2]],dist=Math.hypot(d[0],d[1],d[2]);if(!dist)continue;
    const dot=vdot(f,d)/dist,tn=gameKey(ei,'targetname'),hp=parseFloat(k.health);
    const head=R.num+':'+R.rad+(tn?':'+tn:'')+(isFinite(hp)&&hp?':'+hp.toFixed(1):'');
    const T=(z,s)=>ENTTEXT.push({p:[o[0],o[1],o[2]+z],s:s});
    if(R.g==='actor'){
      if(v!==4&&(!(dot>0.9||(dot>0&&dist<256))||dist>=maxd||dist<=64))continue;
      const r=actorRadii(ei);
      T(B.maxs[2]+56,R.num+':'+R.rad+':'+tn+':'+r.health.toFixed(1));
      T(B.maxs[2]+20,'idle');                    // every AI starts in its idle think state
      if(v===1){const home=[o[0],o[1],o[2]+B.maxs[2]+18];
        dl(cen,home,DC.green);dlCircle(home,r.leash,DC.green,true,feet);
        dlCircle(cen,r.mind,DC.red,true,feet);dlCircle(cen,r.maxd,DC.blue,true,feet);}
      else if(v===2){dlCircle(cen,r.hear,DC.red,true,feet);dlCircle(cen,r.sight,DC.blue,true,feet);}
    }else if(R.g==='door'){
      if(!(dot>0.95&&dist<1024&&dist>64))continue;
      const z=(B.mins[2]+B.maxs[2])*0.5;T(z,head);T(z+18,B.door?B.door.state:'closed');
    }else if(R.g==='turret'){
      if(!(dot>0.9||(dot>0&&dist<256))||dist>=2048||dist<=64)continue;
      T(B.maxs[2]+56,R.num+':'+R.rad+':'+tn);T(B.maxs[2]+38,'aim_target: -1');T(B.maxs[2]+20,'owner: -1');
    }else if(R.g!=='weapon'){                    // Weapon::ShowInfo shows nothing
      if(!(dot>0.95&&dist<1024&&dist>64))continue;
      T(B.maxs[2]+65,head);
    }
  }}

// ---- AI path nodes: ai_shownodenums, ai_shownode, ai_showallnode -------------------------
// The node numbers (DrawAllConnections): yellow, 14 units over each node within
// ai_showroutes_distance of the eye.
function dlNodeNums(feet){
  const P=PA(),O=P.o,eye=cam.pos,lim=CVARS.ai_showroutes_distance;
  for(let i=0;i<P.n;i++){const o=[O[i*3],O[i*3+1],O[i*3+2]];
    if(Math.sqrt(dist2(o,eye))>lim)continue;
    dlNumber([o[0],o[1],o[2]+14],i,1.5,DC.yellow,feet);}}
// PathSearch's map cells (256 units, from -8192): every node not marked DONT_LINK is filed
// in the four cells round it, in node order
let PATHCELLS=null;
function pathCells(){
  if(PATHCELLS)return PATHCELLS;
  const P=PA(),O=P.o,F=P.f,cells=new Map();
  const NC=c=>{let v=c+8192-128;if(v<0)v=c+8192+128-1;return Math.trunc(v)>>8;};   // NodeCoordinate
  const add=(x,y,i)=>{if(x<0||x>=64||y<0||y>=64)return;const k=x*64+y;let l=cells.get(k);if(!l){l=[];cells.set(k,l);}l.push(i);};
  for(let i=0;i<P.n;i++){if(F[i]&1)continue;const x=NC(O[i*3]),y=NC(O[i*3+1]);add(x,y,i);add(x+1,y,i);add(x,y+1,i);add(x+1,y+1,i);}
  return PATHCELLS=cells;
}
function gridCoord(c){let v=c+8192;if(v<0)v=c+8192+256-1;return Math.trunc(v)>>8;}   // GridCoordinate
function pnEnts(){if(!PN_ENTS){PN_ENTS=[];MAP.ents.forEach((e,j)=>{if(e.cls==='info_pathnode'&&!e.scr)PN_ENTS.push(j);});}return PN_ENTS;}
// a node's yaw: its info_pathnode's (the .pth keeps nodes in the map's order)
function nodeYaw(i){const pn=pnEnts(),n=pathsOk()?D.paths.n:PA_GEN?PA_GEN.n:-1,ei=pn.length===n?pn[i]:-1;return ei>=0?entAngles(MAP.ents[ei].kvl)[1]:0;}
// GetPathnodeColor, by spawnflags: black for flags the AI can't combine (IsValidPathnode)
function nodeColour(sf){
  if(nodeFlagsBad(sf))return[0,0,0];
  if(sf&16)return[1,1,0];if(sf&32)return[0.7,1,0];if(sf&2)return[0,1,1];if(sf&64)return[1,0,0];
  if(sf&8)return[0,0,1];if(sf&4)return[0,1,0];if(sf&128)return[1,0,0];       // CRATE: (3, 0, 0)
  return[1,0,1];}
// Where the player stands for these: its feet 82 units under the camera, lifted out of a
// brush they would be inside (the game's player never is), at most to the camera
function standFeet(feet){
  const p=feet.slice();
  for(let dz=0;dz<=VIEWHEIGHT;dz++){p[2]=feet[2]+dz;if(sightTrace(p,p))return p;}
  return feet;
}
let NODELIST=null;
// DrawNode's list: DebugNearestNodeList (the nodes of the player's cell within 94 units
// of its height, nearest first, those a 30 x 30 x 62 box can reach, at most N; none
// reachable: the nearest) or with ai_showallnode DebugNearestNodeList2 (every node at
// that height, nearest first; N doesn't limit it)
function nodeList(feet0,N){
  const key=feet0.map(v=>Math.round(v)).join(',')+':'+N+':'+CVARS.ai_showallnode;
  if(NODELIST&&NODELIST.key===key)return NODELIST;
  const feet=standFeet(feet0),P=PA(),O=P.o,list=[];
  if(CVARS.ai_showallnode){
    const d=[];for(let i=0;i<P.n;i++){const z=O[i*3+2];if(feet[2]>z+94||z>feet[2]+94)continue;
      d.push([dist2([O[i*3],O[i*3+1],z],feet),i]);}
    d.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);for(const x of d)list.push(x[1]);
  }else{
    const gx=gridCoord(feet[0]),gy=gridCoord(feet[1]);
    const cell=(gx>=0&&gx<64&&gy>=0&&gy<64)?pathCells().get(gx*64+gy):null;
    if(cell){
      const order=[],deltas=[];                  // NearestNodeSetup: deltas in the cell's order, the order by distance
      for(let i=0;i<cell.length;i++){const j=cell[i],z=O[j*3+2];
        if(feet[2]>z+94||feet[2]+94<z)continue;
        deltas[i]=[O[j*3]-feet[0],O[j*3+1]-feet[1],z-feet[2]];
        const dd=vdot(deltas[i],deltas[i]);let k=order.length;while(k>0&&dd<order[k-1][0])k--;order.splice(k,0,[dd,i]);}
      for(let r=0;r<order.length&&list.length<N;r++){
        // the game traces to the delta of the cell's r-th node (it indexes them by rank),
        // which is this node's own only when nothing nearer was left out
        const dv=deltas[r]||deltas[order[r][1]];
        if(sightTrace(feet,[feet[0]+dv[0],feet[1]+dv[1],feet[2]+dv[2]]))list.push(cell[order[r][1]]);}
      if(!list.length&&order.length)list.push(cell[order[0][1]]);
    }
  }
  return NODELIST={key:key,list:list,feet:feet,lift:feet[2]-feet0[2]};
}
// DrawNode: a 31 x 31 x 36 box in the node's colour and a white line 16 units along its yaw,
// 18 up; no node at all: a red circle round the player
function dlNodes(feet){
  const N=Math.min(CVARS.ai_shownode,4096),L=nodeList(feet,N),list=L.list,P=PA(),O=P.o,F=P.f;
  if(!list.length){const f=L.feet;dlCircle([f[0],f[1],f[2]+48],128,DC.red,true,feet);return;}
  const q=[[15.5,15.5],[15.5,-15.5],[-15.5,-15.5],[-15.5,15.5]];
  for(const i of list){const o=[O[i*3],O[i*3+1],O[i*3+2]],c=nodeColour(F[i]),y=paYaw(i)*Math.PI/180;
    dl([o[0],o[1],o[2]+18],[o[0]+Math.cos(y)*16,o[1]+Math.sin(y)*16,o[2]+18],DC.white);
    for(let a=0;a<4;a++){const p=q[a],r=q[(a+1)%4];
      dl([o[0]+p[0],o[1]+p[1],o[2]+36],[o[0]+r[0],o[1]+r[1],o[2]+36],c);
      dl([o[0]+p[0],o[1]+p[1],o[2]],[o[0]+r[0],o[1]+r[1],o[2]],c);
      dl([o[0]+p[0],o[1]+p[1],o[2]+36],[o[0]+p[0],o[1]+p[1],o[2]],c);}}}
// G_SightTrace with the 30 x 30 x 62 box as the game's capsule (a sphere of radius 15
// swept along 32 units upright, CM_TraceThroughBrush), against the world's brushes whose
// contents MASK_PATHSOLID stops; patches, terrain and entities (doors, the AI) don't stop
// it here. Each brush gets its six axial planes, as the compiler adds them (bevels).
const MASK_PATHSOLID=0x1|0x40000000|0x2000000|0x2000|0x800|0x100|0x20000;
const CLEARS_SOLID=new Set(['water','slime','lava','playerclip','monsterclip','fence','weaponclip','vehicleclip','nodrop','nonsolid','origin','areaportal','fog','alphashadow']);
let TRACEBR=null;
function traceBrushes(){
  if(TRACEBR)return TRACEBR;
  const L=[];
  for(const p of SC.prims){if(p.kind!==0||!WORLDLIKE[MAP.ents[p.ent].cls]||!isFinite(p.mins[0]))continue;
    const pr=MAP.ents[p.ent].prims[p.bn];if(!pr||!pr.d||!pr.d.faces.length)continue;
    // the brush's contents: its first side's, as the compiled .bsp has them on the face,
    // else its shader's (solid unless a surfaceparm clears it)
    const faces=pr.d.faces,f0=faces[0],te=texFor(f0.tex);
    let c=(f0.cont|0)&~0x8000000;
    if(!c){c=(te.cf|0)|((te.p||[]).some(x=>CLEARS_SOLID.has(x))?0:1);}
    if(!(c&MASK_PATHSOLID))continue;
    const pl=[];for(const f of faces){const q=planeOf(f);if(q)pl.push(q);}
    const mn=p.mins,mx=p.maxs;
    pl.push([1,0,0,mx[0]],[-1,0,0,-mn[0]],[0,1,0,mx[1]],[0,-1,0,-mn[1]],[0,0,1,mx[2]],[0,0,-1,-mn[2]]);
    L.push({mn:mn,mx:mx,pl:pl});}
  return TRACEBR=L;
}
function sightTrace(a,b){
  const s=[a[0],a[1],a[2]+31],e=[b[0],b[1],b[2]+31],R=15,EPS=0.125;
  const lo=[Math.min(a[0],b[0])-16,Math.min(a[1],b[1])-16,Math.min(a[2],b[2])-1],hi=[Math.max(a[0],b[0])+16,Math.max(a[1],b[1])+16,Math.max(a[2],b[2])+63];
  for(const B of traceBrushes()){
    if(B.mn[0]>hi[0]||B.mx[0]<lo[0]||B.mn[1]>hi[1]||B.mx[1]<lo[1]||B.mn[2]>hi[2]||B.mx[2]<lo[2])continue;
    let enter=-1,leave=1,out=false,miss=false;
    for(const q of B.pl){
      const dist=Math.abs(q[2]*16)+q[3]+R, d1=s[0]*q[0]+s[1]*q[1]+s[2]*q[2]-dist, d2=e[0]*q[0]+e[1]*q[1]+e[2]*q[2]-dist;
      if(d1<=0&&d2<=0)continue;
      if(d1>0)out=true;
      if(d1>0&&(d2>=EPS||d2>=d1)){miss=true;break;}
      if(d1>d2){const f=Math.max(0,(d1-EPS)/(d1-d2));if(f>enter)enter=f;}
      else{const f=Math.min(1,(d1+EPS)/(d1-d2));if(f<leave)leave=f;}
    }
    if(miss)continue;
    if(!out)return false;                        // starts inside the brush
    if(enter<leave&&enter>-1)return false;
  }
  return true;
}

// ---- AI path generation: PathSearch::CreatePaths (navigate.cpp, g_mmove.cpp) ---------------
// How the game links its path nodes when it builds a .pth, for the nodes MODIFY adds. Each
// node is dropped to the floor (droptofloor: a 31 x 31 box, 36 up and 2048 down); a node at
// the same spot as an earlier one is a duplicate and gets PATH_DONT_LINK. Every node is
// filed in the four 256-unit cells round it and tries each node of the 3 x 3 cells about
// its own (at most 48 links a node): a pair under 384 units apart (flat) links one way
// when CheckMove gets there: a 31 x 31 x 94 box walking at 150 units a second, 0.1 s a
// step, at most 200 steps, through the AI's movement code (MmoveSingle: slide along walls,
// step up 18 units, fall with gravity 800), stopping at a wall it can't get past, a fall
// higher than 1024 units, or arriving more than 94 units off the other node's height.
// The fall on the way is the link's fall height, which ai_fallheight later checks.
// The box meets what MASK_PATHSOLID stops: the world's solid, monsterclip and fence brushes,
// patches and terrain, and the brush entities other than doors (CreatePaths unlinks the
// doors while it runs) and triggers; not playerclip.
const PG_CELL=512, PG_WALK=0.7, PG_OVERCLIP=1.001, PG_STEP=18, PG_MAXSZ=94, PG_GRAV=800;
let PG=null,PG_PRE=null;
// brush entities the game doesn't make solid (func_rain is the client's weather volume)
const PG_NOTSOLID={func_rain:1,func_ladder:1};
function pgCont(cont,te){let c=(cont|0)&~CONTENTS_DETAIL;if(!c)c=(te.cf|0)|((te.p||[]).some(x=>CLEARS_SOLID.has(x))?0:1);return c;}
function pgEntSolid(ei){
  if(ei===0||WORLDLIKE[MAP.ents[ei].cls])return 0;          // part of the world
  const cls=MAP.ents[ei].cls;
  if(DOOR_CLASSES[cls]||cls.startsWith('trigger_')||PG_NOTSOLID[cls]||MAP.ents[ei].scr)return -1;
  // the level script's "$x solid" / "$x notsolid" before "level waittill prespawn"
  if(!PG_PRE){PG_PRE=new Map();for(const[k,v]of(D.scr&&D.scr.presolid)||[])PG_PRE.set(k,v);}
  if(PG_PRE.has(ei))return PG_PRE.get(ei)?ei:-1;
  // a brush entity made only of common/trigger (a script_object the level script uses as a
  // volume, "isTouching") never blocks the paths in the game's own .pth files
  const pr=MAP.ents[ei].prims;
  if(pr.length&&pr.every(p=>p&&p.kind===0&&p.d&&p.d.faces.every(f=>/(^|\/)common\/trigger$/i.test(f.tex))))return -1;
  // exploder.scr makes the smashed pieces and the chunks notsolid as the level loads, before
  // the paths are made
  const r=expRole(ei);if(r==='smashed'||r==='chunk')return -1;
  return ei;
}
let PG_BC=null;
function pgBcont(ei,bn){
  if(!PG_BC){PG_BC=new Map();const B=D.bsp&&D.bsp.bcont;if(B)for(const k in B)for(const[b,c]of B[k])PG_BC.set(+k*65536+b,c);}
  const v=PG_BC.get(ei*65536+bn);return v==null?null:v;
}
function pgSolids(){
  if(PG)return PG;
  const L=[],TC=[];
  const bevel=(pl,mn,mx)=>{pl.push([1,0,0,mx[0]],[-1,0,0,-mn[0]],[0,1,0,mx[1]],[0,-1,0,-mn[1]],[0,0,1,mx[2]],[0,0,-1,-mn[2]]);};
  // a patch triangle: a facet, front side only, with its edges and the axial bevels
  // (CM_TraceThroughPatchCollide, the box always; patches don't take the capsule)
  const facet=(ent,a,b,c)=>{
    let n=vnorm(vcross(vsub(b,a),vsub(c,a)));if(!n)return;
    const d=vdot(n,a),pl=[[n[0],n[1],n[2],d],[-n[0],-n[1],-n[2],-(d-1)]];
    const P=[a,b,c];
    for(let i=0;i<3;i++){const p=P[i],q=P[(i+1)%3],r=P[(i+2)%3];let e=vnorm(vcross(vsub(q,p),n));if(!e)continue;
      if(vdot(e,vsub(r,p))>0)e=[-e[0],-e[1],-e[2]];pl.push([e[0],e[1],e[2],vdot(e,p)]);}
    const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
    for(const p of P)for(let k=0;k<3;k++){if(p[k]<mn[k])mn[k]=p[k];if(p[k]>mx[k])mx[k]=p[k];}
    bevel(pl,mn,mx);L.push({ent:ent,mn:mn,mx:mx,pl:pl,patch:true});};
  const pt=v=>[SC.pos[v*3],SC.pos[v*3+1],SC.pos[v*3+2]];
  for(const p of SC.prims){
    if(!isFinite(p.mins[0])||p.kind===2)continue;
    const ent=pgEntSolid(p.ent);if(ent<0)continue;
    const pr=MAP.ents[p.ent].prims[p.bn];if(!pr||!pr.d)continue;
    if(p.kind===0){const faces=pr.d.faces;if(!faces.length)continue;
      // the brush's own contents (from the .bsp, where they differ from its first face's)
      const bc=pgBcont(p.ent,p.bn),c=pgCont(bc!=null?bc:faces[0].cont,texFor(faces[0].tex));
      if(!(c&MASK_PATHSOLID))continue;
      const pl=[];for(const f of faces){const q=planeOf(f);if(q)pl.push(q);}
      if(!pl.length)continue;bevel(pl,p.mins,p.maxs);
      L.push({ent:ent,mn:p.mins.slice(),mx:p.maxs.slice(),pl:pl,patch:false,pi:SC.prims.indexOf(p)});}
    else if(p.kind===1){
      if(!(pgCont(pr.d.cont,texFor(pr.d.tex))&MASK_PATHSOLID))continue;
      for(let f=p.f0;f<p.f1;f++){const i0=SC.faceI0[f],n=SC.faceIN[f]/3;
        for(let t=0;t<n;t++){if((t%4)>=2)continue;const q=i0+t*3;facet(ent,pt(SC.tri[q]),pt(SC.tri[q+1]),pt(SC.tri[q+2]));}}}
  }
  // terrain: CM_GenerateTerrainCollide, each 64-unit square two planes, or one where the
  // other triangle is cut away; terrain always collides, whatever the trace's mask
  const PFP=(a,b,c)=>{const n=vnorm(vcross(vsub(c,a),vsub(b,a)));return n?[n[0],n[1],n[2],vdot(a,n)]:[0,0,0,0];};
  const MT=[2,2,5,6,4,3,0,0];
  MAP.ents.forEach((e,ei)=>{if(!WORLDLIKE[e.cls])return;
    for(const tp of e.terrains){const T=tp.d;if(!T||T.W!==9||T.H!==9)continue;
      const x0=T.org[0],y0=T.org[1],z0=T.org[2],H=(i,j)=>z0+T.heights[j*9+i];let mx=z0;
      const sq=[];
      for(let i=0;i<8;i++){sq.push([]);for(let j=0;j<8;j++){
        const v1=[x0+i*64,y0+j*64,H(i,j)],v2=[x0+i*64+64,y0+j*64,H(i+1,j)],v3=[x0+i*64+64,y0+j*64+64,H(i+1,j+1)],v4=[x0+i*64,y0+j*64+64,H(i,j+1)];
        mx=Math.max(mx,v1[2],v2[2],v3[2],v4[2]);
        const odd=(i+j)&1,k=j*9+i,h1=T.hole1[k],h2=T.hole2[k];
        const p0=odd?PFP(v2,v4,v3):PFP(v3,v1,v4),p1=odd?PFP(v4,v2,v1):PFP(v1,v3,v2);
        const hole0=odd?h1:h2,hole1=odd?h2:h1;
        let m=MT[odd|(hole0?2:0)|(hole1?4:0)];const vt=odd?v1:v2,s={p:[p0,p1],m:0};
        if(m===2){if(vdot(vt,p0)<p0[3])m=1;}else if(m===5||m===6)s.p[0]=p1.slice();
        s.m=m;sq[i].push(s);}}
      TC.push({b0:[x0,y0,z0],b1:[x0+512,y0+512,mx],sq:sq});}});
  const cells=new Map();
  L.forEach((B,i)=>{const x0=Math.floor(B.mn[0]/PG_CELL),x1=Math.floor(B.mx[0]/PG_CELL),y0=Math.floor(B.mn[1]/PG_CELL),y1=Math.floor(B.mx[1]/PG_CELL);
    for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){const k=x*4096+y;let c=cells.get(k);if(!c){c=[];cells.set(k,c);}c.push(i);}});
  return PG={L:L,TC:TC,cells:cells,stamp:new Uint32Array(L.length),sn:0};
}
// ---- terrain collision (cm_terrain.c, the original game's version)
function pgTerPlane(pt,pl){
  const d1=vdot(pt.s,pl)-pl[3],d2=vdot(pt.e,pl)-pl[3];
  if(d1>0&&(d2>=0.125||d2>=d1))return 1;
  if(d1<=0&&d2<=0){if(d1>=-32)return 0;if(d2>=-32)return 0;return 1;}
  if(d1<=d2)return 1;
  return Math.max(0,(d1-0.125)/(d1-d2));
}
function pgTerSqOk(pt,f){
  let x=pt.s[0]+f*(pt.e[0]-pt.s[0])-(pt.i*64+pt.tc.b0[0]);
  if(x>=0&&x<=64){x=pt.s[1]+f*(pt.e[1]-pt.s[1])-(pt.j*64+pt.tc.b0[1]);if(x>=0&&x<=64)return true;}
  return false;
}
function pgTerTriOk(pt,m,f){
  const x0=pt.i*64+pt.tc.b0[0],dx=pt.s[0]+(pt.e[0]-pt.s[0])*f;if(x0>dx||x0+64<dx)return false;
  const y0=pt.j*64+pt.tc.b0[1],dy=pt.s[1]+(pt.e[1]-pt.s[1])*f;if(y0>dy||y0+64<dy)return false;
  if(m===3)return(dx-x0)>=(64-(dy-y0));if(m===4)return(dx-x0)<=(dy-y0);
  if(m===5)return(dx-x0)>=(dy-y0);if(m===6)return(dx-x0)<=(64-(dy-y0));return true;
}
function pgTerSquare(pt){
  const S=pt.tc.sq[pt.i][pt.j],m=S.m,tw=pt.tw;
  if(!m)return false;
  if(m<=2){
    let ef=pgTerPlane(pt,S.p[0]);const pl=S.p[1],f0=pgTerPlane(pt,pl);
    if(m===2){if(ef>f0)ef=f0;}else if(ef<f0)ef=f0;
    if(ef<tw.f&&pgTerSqOk(pt,ef)){tw.f=ef;tw.n=pl.slice(0,3);tw.ent=0;return true;}
  }else{
    const pl=S.p[0],ef=pgTerPlane(pt,pl);
    if(ef<tw.f&&pgTerTriOk(pt,m,ef)){tw.f=ef;tw.n=pl.slice(0,3);tw.ent=0;return true;}
  }
  return false;
}
function pgTerInside(pt,i,j,fx,fy){
  if(i<0||i>7||j<0||j>7)return false;
  const S=pt.tc.sq[i][j];if(!S.m)return false;let pl;
  if((i+j)&1){if(fx+fy>=1){if(S.m===6)return false;pl=S.p[0];}else{if(S.m===3)return false;pl=S.p[1];}}
  else{if(fy>=fx){if(S.m===5)return false;pl=S.p[0];}else{if(S.m===4)return false;pl=S.p[1];}}
  const d=vdot(pt.s,pl);return d<=pl[3]&&d+32>=pl[3];
}
function pgTerPoint(pt){
  const tc=pt.tc,tw=pt.tw,fx=(pt.s[0]-tc.b0[0])/64,fy=(pt.s[1]-tc.b0[1])/64;
  let i0=Math.floor(fx),j0=Math.floor(fy),i1=Math.floor((pt.e[0]-tc.b0[0])/64),j1=Math.floor((pt.e[1]-tc.b0[1])/64);
  const dfx=fx-i0,dfy=fy-j0;
  if(pgTerInside(pt,i0,j0,dfx,dfy)){tw.startsolid=tw.allsolid=true;tw.f=0;tw.ent=0;return;}
  if(i0===i1){
    if(i0<0||i0>7)return;
    if(j0===j1){if(j0<0||j0>7)return;pt.i=i0;pt.j=j0;pgTerSquare(pt);}
    else if(j0>=j1){if(j0>7)j0=7;if(j1<0)j1=0;pt.i=i0;for(pt.j=j0;pt.j>=j1;pt.j--)if(pgTerSquare(pt))return;}
    else{if(j0<0)j0=0;if(j1>7)j1=7;pt.i=i0;for(pt.j=j0;pt.j<=j1;pt.j++)if(pgTerSquare(pt))return;}
  }else if(j0===j1){
    if(j0<0||j0>7)return;
    if(i0>=i1){if(i0>7)i0=7;if(i1<0)i1=0;pt.j=j0;for(pt.i=i0;pt.i>=i1;pt.i--)if(pgTerSquare(pt))break;}
    else{if(i0<0)i0=0;if(i1>7)i1=7;pt.j=j0;for(pt.i=i0;pt.i<=i1;pt.i++)if(pgTerSquare(pt))break;}
  }else{
    let dx=pt.e[0]-pt.s[0],dy=pt.e[1]-pt.s[1],d1,d2,di,dj,dx2,dy2;
    if(i1>i0){d1=1;di=i1-i0;dx2=(i0+1-fx)*dy;}else{d1=-1;di=i0-i1;dx=-dx;dx2=dfx*dy;}
    if(j1>j0){d2=1;dj=di+j1-j0+1;dy2=(j0+1-fy)*dx;}else{d2=-1;dy=-dy;dj=di+j0-j1+1;dy2=dfy*dx;dx2=-dx2;}
    pt.i=i0;pt.j=j0;
    for(;;){
      if(pt.i>=0&&pt.i<=7&&pt.j>=0&&pt.j<=7&&pgTerSquare(pt))return;
      if(!--dj)break;
      if(dx2<dy2){dy2-=dx2;dx2=dy;pt.i+=d1;}else{dx2-=dy2;dy2=dx;pt.j+=d2;}
    }
  }
}
function pgSphPoint(pt,v){
  const tw=pt.tw,r=pt.r,dir=vsub(pt.s,v),r2=r*r,l2=vdot(dir,dir);
  if(l2<=r2){tw.startsolid=tw.allsolid=true;return 0;}
  const dl=vsub(pt.e,pt.s),A=vdot(dl,dl),B=vdot(dl,dir),disc=B*B-(l2-r2)*A;
  if(disc<=0)return tw.f;
  const sq=Math.sqrt(disc);let fr;
  if(A>0){fr=(-B-sq)/A-pt.eps;if(fr>=0&&fr<=tw.f)return fr;fr=-B+sq;}
  else{fr=(-B+sq)/A-pt.eps;if(fr>=0&&fr<=tw.f)return fr;fr=-B-sq;}
  let f=fr/A-pt.eps;if(f<0||f>tw.f)f=tw.f;return f;
}
function pgSphCorner(pt,pl,x0,y0,i,j){const v=[i*64+x0,j*64+y0,0];v[2]=(pl[3]-(v[1]*pl[1]+v[0]*pl[0]))/pl[2];return pgSphPoint(pt,v);}
function pgSphEdge(pt,pl,x0,y0,i0,j0,i1,j1){
  const tw=pt.tw,sc=1/pl[2];
  const v0=[i0*64+x0,j0*64+y0,0];v0[2]=(pl[3]-(v0[0]*pl[0]+v0[1]*pl[1]))*sc;
  const v1=[i1*64+x0,j1*64+y0,0];v1[2]=(pl[3]-(v1[0]*pl[0]+v1[1]*pl[1]))*sc;
  const dt=vsub(pt.s,v0),de=vsub(v1,v0),ds=vsub(pt.e,pt.s),s2=1/vdot(de,de),S=vdot(dt,de)*s2,T=vdot(ds,de)*s2;
  const rc=[dt[0]-S*de[0],dt[1]-S*de[1],dt[2]-S*de[2]],rs=[ds[0]-T*de[0],ds[1]-T*de[1],ds[2]-T*de[2]];
  const r2=pt.r*pt.r,l2=vdot(rc,rc);
  if(l2<=r2){if(S<0||S>1)return pgSphPoint(pt,v0);tw.startsolid=tw.allsolid=true;return 1;}
  const dot=vdot(rs,rc),ss=vdot(rs,rs),sc2=dot*dot-(l2-r2)*ss;
  if(sc2<=0)return tw.f;
  let fr=ss>0?(-dot-Math.sqrt(sc2))/ss:(-dot+Math.sqrt(sc2))/ss;
  if(fr<=0)return tw.f;
  let fc=fr-pt.eps;if(fc>=tw.f)return tw.f;
  fr=fr*T+S;
  if(fr<0)return pgSphPoint(pt,v0);if(fr>1)return pgSphPoint(pt,v1);
  return fc<0?0:fc;
}
function pgSphTri(pt,x0,y0,ip){
  const tw=pt.tw,r=pt.r,S=pt.tc.sq[pt.i][pt.j],pl=S.p[ip];
  let d1=vdot(pt.s,pl)-pl[3],d2=vdot(pt.e,pl)-pl[3];
  if(d1>r&&(d2>=r+0.125||d2>=d1))return tw.f;
  if(d1<=-r&&d2<=-r)return tw.f;
  if(d1<=d2)return tw.f;
  const fm=0.125/(d1-d2);pt.eps=fm;
  let sp=(d1-r)/(d1-d2)-fm;if(sp<0)sp=0;
  if(sp>=tw.f)return tw.f;
  d1=(pt.e[0]-pt.s[0])*sp+pt.e[0]-r*pl[0]-x0;
  d2=(pt.e[1]-pt.s[1])*sp+pt.e[1]-r*pl[1]-y0;
  let m=S.m;if(m===1||m===2)m=((pt.i+pt.j)&1)?(ip?6:3):(ip?5:4);
  let fx,fy,fd,X,Y;
  if(m===3){fx=d1<=64;fy=d2<=64;fd=d1>=64-d2;X=[1,0,1];Y=[1,1,0];}
  else if(m===4){fx=d1>=0;fy=d2<=64;fd=d1<=d2;X=[0,1,0];Y=[1,1,0];}
  else if(m===5){fx=d1<=64;fy=d2>=0;fd=d1>=d2;X=[1,0,1];Y=[0,0,1];}
  else if(m===6){fx=d1>=0;fy=d2>=0;fd=d1<=64-d2;X=[0,1,0];Y=[0,0,1];}
  else return 0;
  if(fx&&fy)return fd?sp:pgSphEdge(pt,pl,x0,y0,X[1],Y[1],X[2],Y[2]);
  if(fx&&!fy)return fd?pgSphEdge(pt,pl,x0,y0,X[0],Y[0],X[1],Y[1]):pgSphCorner(pt,pl,x0,y0,X[1],Y[1]);
  if(!fx&&fy)return fd?pgSphEdge(pt,pl,x0,y0,X[0],Y[0],X[2],Y[2]):pgSphCorner(pt,pl,x0,y0,X[2],Y[2]);
  if(fd)return pgSphCorner(pt,pl,x0,y0,X[0],Y[0]);
  return tw.f;
}
function pgTerCyl(pt,b0,b1){
  const tc=pt.tc,tw=pt.tw;
  let i0=Math.trunc(Math.floor(b0[0]-tc.b0[0])/64),i1=Math.trunc(Math.floor(b1[0]-tc.b0[0])/64),
      j0=Math.trunc(Math.floor(b0[1]-tc.b0[1])/64),j1=Math.trunc(Math.floor(b1[1]-tc.b0[1])/64);
  if(i0<0)i0=0;if(j0<0)j0=0;if(i1>7)i1=7;if(j1>7)j1=7;
  let y0=j0*64+tc.b0[1];
  for(pt.j=j0;pt.j<=j1;pt.j++){let x0=i0*64+tc.b0[0];
    for(pt.i=i0;pt.i<=i1;pt.i++){const S=tc.sq[pt.i][pt.j],m=S.m;
      const one=ip=>{let f=pgSphTri(pt,x0,y0,ip);if(f<0)f=0;if(f<tw.f){tw.f=f;tw.n=S.p[ip].slice(0,3);tw.ent=0;}};
      if(m===1||m===2){one(0);one(1);}else if(m===3||m===4)one(0);else if(m===5||m===6)one(1);
      x0+=64;}
    y0+=64;}
}
// gi.trace of a box from s to e (CM_BoxTrace with SV_ClipMoveToEntities): with cyl (as the
// AI's movement traces) brushes and terrain see a capsule, the box's width round, as the
// game's "cylinder" traces do. Returns the fraction, end, the plane met, start/all solid,
// and what it met: -1 nothing, 0 the world, else the entity.
function pgTrace(s,e,mins,maxs,cyl){
  const G=pgSolids(),EPS=0.125;
  const off=[(mins[0]+maxs[0])/2,(mins[1]+maxs[1])/2,(mins[2]+maxs[2])/2],hs=[maxs[0]-off[0],maxs[1]-off[1],maxs[2]-off[2]];
  const S=[s[0]+off[0],s[1]+off[1],s[2]+off[2]],E=[e[0]+off[0],e[1]+off[1],e[2]+off[2]];
  const sr=cyl?(hs[0]>hs[2]?hs[2]:hs[0]):0,so=cyl?hs[2]-sr:0;
  const b0=[Math.min(S[0],E[0])-hs[0],Math.min(S[1],E[1])-hs[1],Math.min(S[2],E[2])-hs[2]],
        b1=[Math.max(S[0],E[0])+hs[0],Math.max(S[1],E[1])+hs[1],Math.max(S[2],E[2])+hs[2]];
  const tw={f:1,n:[0,0,0],ent:-1,startsolid:false,allsolid:false};
  const done=()=>{const f=tw.f;tw.end=f===1?e.slice():[s[0]+f*(e[0]-s[0]),s[1]+f*(e[1]-s[1]),s[2]+f*(e[2]-s[2])];if(tw.allsolid)tw.n=[0,0,0];if(f===1)tw.ent=-1;return tw;};
  const sn=++G.sn,lo0=b0[0]-1,lo1=b0[1]-1,lo2=b0[2]-1,hi0=b1[0]+1,hi1=b1[1]+1,hi2=b1[2]+1;
  const x0=Math.floor(lo0/PG_CELL),x1=Math.floor(hi0/PG_CELL),y0=Math.floor(lo1/PG_CELL),y1=Math.floor(hi1/PG_CELL);
  for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){const c=G.cells.get(x*4096+y);if(!c)continue;
    for(const i of c){if(G.stamp[i]===sn)continue;G.stamp[i]=sn;const B=G.L[i];
      if(B.mn[0]>hi0||B.mx[0]<lo0||B.mn[1]>hi1||B.mx[1]<lo1||B.mn[2]>hi2||B.mx[2]<lo2)continue;
      const caps=cyl&&!B.patch;
      let enter=-1,leave=1,clip=null,startout=false,getout=false,miss=false;
      for(const q of B.pl){
        const dist=caps?Math.abs(q[2]*so)+q[3]+sr:q[3]+hs[0]*Math.abs(q[0])+hs[1]*Math.abs(q[1])+hs[2]*Math.abs(q[2]);
        const d1=S[0]*q[0]+S[1]*q[1]+S[2]*q[2]-dist,d2=E[0]*q[0]+E[1]*q[1]+E[2]*q[2]-dist;
        if(d1<=0&&d2<=0)continue;
        if(d2>0)getout=true;
        if(d1>0)startout=true;
        if(d1>0&&(d2>=EPS||d2>=d1)){miss=true;break;}
        if(d1>d2){let g=(d1-EPS)/(d1-d2);if(g<0)g=0;if(g>enter){enter=g;clip=q;}}
        else{let g=(d1+EPS)/(d1-d2);if(g>1)g=1;if(g<leave)leave=g;}
      }
      if(miss)continue;
      if(B.patch){if(enter<=leave&&enter>=0&&enter<tw.f&&clip&&clip!==B.pl[1]){tw.f=enter;tw.n=[clip[0],clip[1],clip[2]];tw.ent=B.ent;}continue;}
      if(!startout){tw.startsolid=true;if(!getout){tw.allsolid=true;tw.f=0;tw.ent=B.ent;return done();}continue;}
      if(enter<leave&&enter>-1&&enter<tw.f){tw.f=Math.max(0,enter);tw.n=[clip[0],clip[1],clip[2]];tw.ent=B.ent;tw.pi=B.pi;}
    }}
  for(const tc of G.TC){
    if(b0[0]>=tc.b1[0]||b1[0]<=tc.b0[0]||b0[1]>=tc.b1[1]||b1[1]<=tc.b0[1]||b0[2]>=tc.b1[2]||b1[2]<=tc.b0[2])continue;
    if(cyl){const pt={tw:tw,tc:tc,s:[S[0],S[1],S[2]-so],e:[E[0],E[1],E[2]-so],i:0,j:0,eps:0,r:sr};pgTerCyl(pt,b0,b1);}
    else for(let k=0;k<4;k++){
      const o=[k&1?hs[0]:-hs[0],k&2?hs[1]:-hs[1],-hs[2]];
      const pt={tw:tw,tc:tc,s:[S[0]+o[0],S[1]+o[1],S[2]+o[2]],e:[E[0]+o[0],E[1]+o[1],E[2]+o[2]],i:0,j:0};
      pgTerPoint(pt);if(tw.allsolid)break;}
    if(tw.allsolid)break;
  }
  return done();
}
const PG_BASE_MIN=[-15.5,-15.5,0],PG_BASE_MAX=[15.5,15.5,0];
function pgDrop(v){const s=[v[0],v[1],v[2]+36],t=pgTrace(s,[s[0],s[1],s[2]-2048],PG_BASE_MIN,PG_BASE_MAX,false);return[v[0],v[1],t.end[2]];}
// ---- g_mmove.cpp
function pgDot2(a,b){return a[0]*b[0]+a[1]*b[1];}
function pgNorm(v){const l=Math.hypot(v[0],v[1],v[2]);if(l){v[0]/=l;v[1]/=l;v[2]/=l;}return l;}
function pgClipVel(i,n,o,ob){
  if(n[2]>=PG_WALK){
    if(i[0]*i[0]+i[1]*i[1]<0.005){o[0]=o[1]=o[2]=0;return;}
    const d=pgDot2(i,n),n2=[i[0]*d,i[1]*d,n[2]*pgDot2(i,i)];pgNorm(n2);
    const dz=-n2[2],x=i[0],y=i[1];o[0]=x;o[1]=y;o[2]=(x*n2[0]+y*n2[1])/dz;
  }else{let b=vdot(i,n);b=b<0?b*ob:b/ob;o[0]=i[0]-n[0]*b;o[1]=i[1]-n[1]*b;o[2]=i[2]-n[2]*b;}
}
function pgClipVel2D(i,n,o,ob){
  if(n[2]>=PG_WALK){
    if(i[0]===0&&i[1]===0){o[0]=o[1]=o[2]=0;return;}
    const d=pgDot2(i,n),n2=[i[0]*d,i[1]*d,n[2]*pgDot2(i,i)];pgNorm(n2);
    const dz=-n2[2],x=i[0],y=i[1];o[0]=x;o[1]=y;o[2]=(x*n2[0]+y*n2[1])/dz;
  }else{let b=pgDot2(i,n);b=b<0?b*ob:b/ob;o[0]=i[0]-n[0]*b;o[1]=i[1]-n[1]*b;o[2]=-(b*n[2]);}
}
function pgTr(mm,a,b){return pgTrace(a,b,mm.mins,mm.maxs,true);}
function pgTouch(e){return true;}        // the world and every solid brush entity block the AI
function pgSlide(mm,ml,grav){
  if(grav){mm.vel[2]-=mm.ft*PG_GRAV;if(mm.ground)pgClipVel(mm.vel,mm.gn,mm.vel,PG_OVERCLIP);}
  let tl=mm.ft,np=0,tr=null;const planes=[];
  if(mm.ground){planes.push(mm.gn.slice());np=1;}
  {const v=mm.vel.slice();pgNorm(v);planes.push(v);np++;}
  for(let bump=0;bump<4;bump++){
    const end=[mm.o[0]+tl*mm.vel[0],mm.o[1]+tl*mm.vel[1],mm.o[2]+tl*mm.vel[2]];
    tr=pgTr(mm,mm.o,end);
    if(tr.allsolid)break;
    if(tr.f>0)mm.o=tr.end.slice();
    if(tr.f===1)return bump!==0;
    const blk=pgTouch(tr.ent);
    if(tr.n[2]<PG_WALK){
      if(tr.n[2]>-0.999&&blk&&mm.ground){if(!mm.hit){mm.hit=true;mm.hitO=mm.o.slice();}
        for(let k=0;k<3;k++)mm.obn[k]+=tr.n[k];}
    }else{ml.gt=tr;ml.valid=true;}
    tl-=tl*tr.f;
    if(np>=5){mm.vel=[0,0,0];return true;}
    let i;
    for(i=0;i<np;i++)if(vdot(tr.n,planes[i])>0.99){for(let k=0;k<3;k++)mm.vel[k]+=tr.n[k];break;}
    if(i>=np){
      planes.push(tr.n.slice());np++;
      for(i=0;i<np;i++){
        if(vdot(mm.vel,planes[i])>=0.1)continue;
        const cv=[0,0,0];pgClipVel(mm.vel,planes[i],cv,PG_OVERCLIP);
        let stop=false;
        for(let j=0;j<np;j++){
          if(j===i)continue;
          if(vdot(cv,planes[j])>=0.1)continue;
          pgClipVel(cv,planes[j],cv,PG_OVERCLIP);
          if(vdot(cv,planes[i])>=0)continue;
          const dir=vcross(planes[i],planes[j]);pgNorm(dir);const d=vdot(dir,mm.vel);
          cv[0]=dir[0]*d;cv[1]=dir[1]*d;cv[2]=dir[2]*d;
          for(let k=0;k<np;k++){if(k===i||k===j)continue;if(vdot(cv,planes[k])>=0.1)continue;stop=true;break;}
          if(stop)break;
        }
        if(stop){mm.vel=[0,0,0];return true;}
        mm.vel=cv;break;
      }
    }
  }
  if(mm.vel[0]||mm.vel[1]){
    if(mm.ground){const dir=[-mm.vel[0],-mm.vel[1],-mm.vel[2]];pgNorm(dir);
      if(pgTouch(tr.ent)){if(!mm.hit){mm.hit=true;mm.hitO=mm.o.slice();}for(let k=0;k<3;k++)mm.obn[k]+=dir[k];}}
    mm.vel=[0,0,0];return true;
  }
  mm.vel[2]=0;return false;
}
function pgGroundInt(mm,ml){
  const g=ml.gt;
  if(!g||g.f===1){mm.ground=false;mm.walking=false;return;}
  if(mm.vel[2]>0&&vdot(mm.vel,g.n)>10){mm.ground=false;mm.walking=false;return;}
  if(g.n[2]<PG_WALK){
    const old=mm.vel.slice();mm.vel=[0,0,-1/mm.ft];pgSlide(mm,ml,false);
    const d=Math.hypot(mm.vel[0],mm.vel[1],mm.vel[2]);mm.vel=old;
    if(d>0.1/mm.ft){mm.ground=true;mm.walking=false;mm.gn=g.n.slice();return;}
  }
  mm.ground=true;mm.walking=true;mm.gn=g.n.slice();
}
function pgGround(mm,ml){ml.gt=pgTr(mm,mm.o,[mm.o[0],mm.o[1],mm.o[2]-0.25]);pgGroundInt(mm,ml);}
function pgGroundEnd(mm,ml){if(ml.valid)pgGroundInt(mm,ml);else pgGround(mm,ml);}
function pgStepSlide(mm,ml){
  const so=mm.o.slice(),sv=mm.vel.slice(),sHit=mm.hit,sHitO=mm.hitO.slice(),sObn=mm.obn.slice();
  if(!pgSlide(mm,ml,true)){pgGroundEnd(mm,ml);return;}
  let tr=pgTr(mm,so,[so[0],so[1],so[2]-PG_STEP]);
  if(mm.vel[2]>0&&(tr.f===1||tr.n[2]<PG_WALK)){pgGroundEnd(mm,ml);return;}
  const good=mm.ground&&mm.gn[2]>=PG_WALK;
  const nso=mm.o.slice(),nsv=mm.vel.slice(),nsGt=ml.gt,nsValid=ml.valid;
  mm.o=[so[0],so[1],so[2]+18];mm.vel=sv.slice();
  const fHit=mm.hit,fHitO=mm.hitO.slice(),fObn=mm.obn.slice();
  mm.hit=sHit;mm.hitO=sHitO;mm.obn=sObn;
  pgSlide(mm,ml,true);
  tr=pgTr(mm,mm.o,[mm.o[0],mm.o[1],mm.o[2]-PG_STEP*2]);
  if(tr.ent!==0&&tr.ent!==-1){
    mm.o=nso;mm.vel=nsv;ml.gt=nsGt;ml.valid=nsValid;mm.hit=fHit;mm.hitO=fHitO;mm.obn=fObn;
    pgGroundEnd(mm,ml);return;}
  if(!tr.allsolid){
    ml.gt=tr;ml.valid=true;
    if(good&&tr.f<1&&tr.n[2]<PG_WALK){
      mm.o=nso;mm.vel=nsv;
      if(fHit){mm.hit=fHit;mm.hitO=fHitO;mm.obn=fObn;}
      pgGroundInt(mm,ml);return;}
    mm.o=tr.end.slice();
  }
  if(tr.f<1)pgClipVel(mm.vel,tr.n,mm.vel,PG_OVERCLIP);
  pgGroundEnd(mm,ml);
}
function pgMmove(mm){
  mm.hit=false;mm.obn=[0,0,0];
  const ml={valid:false,gt:null},pv=mm.vel.slice();
  if(mm.walking){
    const w=[0,0,0];pgClipVel2D(mm.dd,mm.gn,w,PG_OVERCLIP);pgNorm(w);
    mm.vel[0]=mm.speed*w[0];mm.vel[1]=mm.speed*w[1];
  }else if(mm.ground)pgClipVel(mm.vel,mm.gn,mm.vel,PG_OVERCLIP);
  pgStepSlide(mm,ml);
  if(!mm.walking&&pv[2]>=0&&mm.vel[2]<=0){
    const tr=pgTr(mm,mm.o,[mm.o[0],mm.o[1],mm.o[2]-18]);
    if(tr.f<1&&!tr.allsolid){mm.o=tr.end.slice();pgGround(mm,ml);}
  }
}
// CheckMove: whether the box gets from a to b, and the fall on the way (null: it doesn't)
// A move the game makes from a node on a terrain grid line (x or y a multiple of 64 from the
// terrain's corner) starts "stuck" in the capsule trace here, though the game walks it: the box
// the node was dropped with touches the slope exactly. If the move fails with the actor stuck
// at the start, it is tried again 1 unit up. Compared with m3l1b's .pth (built by the game),
// this finds 65 of the 93 links that are otherwise missed here (and links the two nodes that
// would otherwise show "no paths"), without adding any link the game doesn't make.
function pgCheckMove(a,b,size){
  const r=pgCheckMove1(a,b,size);if(r!=null)return r;
  const t=pgTrace(a,[a[0],a[1],a[2]-0.25],[-size,-size,0],[size,size,PG_MAXSZ],true);
  return t.allsolid?pgCheckMove1([a[0],a[1],a[2]+1],b,size):r;
}
function pgCheckMove1(a,b,size){
  const dd=[b[0]-a[0],b[1]-a[1],0];{const l=Math.hypot(dd[0],dd[1]);if(l){dd[0]/=l;dd[1]/=l;}}
  const mm={o:a.slice(),vel:[0,0,0],speed:150,ft:0.1,dd:dd,ground:false,walking:false,gn:[0,0,1],
    mins:[-size,-size,0],maxs:[size,size,PG_MAXSZ],hit:false,hitO:[0,0,0],obn:[0,0,0]};
  let fall=0,airz=mm.o[2];
  for(let i=0;i<200;i++){
    pgMmove(mm);
    if(mm.ground){
      const tf=airz-mm.o[2];
      if(tf>fall){if(tf>1024)return null;fall=tf;}
      airz=mm.o[2];
    }
    const dir=[b[0]-mm.o[0],b[1]-mm.o[1]];
    if(pgDot2(dir,mm.dd)<=0.1){
      const err=mm.o[2]-b[2];
      if(Math.abs(err)<=PG_MAXSZ){
        if(err<=0||mm.ground)return Math.trunc(fall);
        const tr=pgTrace(mm.o,[mm.o[0],mm.o[1],b[2]],mm.mins,mm.maxs,true),tf=mm.o[2]-tr.end[2];
        if(tf<=18)return tf+fall<=1024?Math.trunc(Math.trunc(tf)+fall):null;
      }
      if(mm.ground)return null;
      const l=Math.hypot(dir[0],dir[1]);mm.dd=l?[dir[0]/l,dir[1]/l,0]:[0,0,0];
    }
    if(mm.hit)break;
  }
  return null;
}
// CheckPathToDefault: a link from node origin a to b ({fall, p1, p2, dist}) or null
function pgLink(a,b){
  const dx=b[0]-a[0],dy=b[1]-a[1],dist=Math.hypot(dx,dy);
  if(dist>=384)return null;
  const s=pgDrop(a),e=pgDrop(b),fall=pgCheckMove(s,e,15.5);
  return fall==null?null:{fall:fall,p1:s,p2:e,dist:dist};
}
// The whole of CreatePaths for nodes at these (spawn) origins with these spawnflags:
// {o: dropped origins, f: flags (DONT_LINK added to duplicates), c: [from, to, fall, p1, p2]...}
function pgCreate(org,flags,only){
  const n=org.length,O=org.map(pgDrop),F=flags.slice();
  for(let i=0;i<n;i++){if(F[i]&1)continue;
    for(let j=i-1;j>=0;j--)if(O[j][0]===O[i][0]&&O[j][1]===O[i][1]&&O[j][2]===O[i][2]){F[i]|=1;break;}}
  const NC=c=>{let v=c+8192-128;if(v<0)v=c+8192+128-1;return Math.trunc(v)>>8;};
  const cells=new Map(),add=(x,y,i)=>{if(x<0||x>=64||y<0||y>=64)return;const k=x*64+y;let l=cells.get(k);if(!l){l=[];cells.set(k,l);}if(l.length<128)l.push(i);};
  for(let i=0;i<n;i++){if(F[i]&1)continue;const x=NC(O[i][0]),y=NC(O[i][1]);add(x,y,i);add(x+1,y,i);add(x,y+1,i);add(x+1,y+1,i);}
  const C=[],over=[];     // over: [full node, the node the game was linking it to when it stopped]
  for(let i=0;i<n;i++){
    if(F[i]&1||(only&&!only(i)))continue;
    const gx=gridCoord(O[i][0]),gy=gridCoord(O[i][1]),seen=new Set([i]);let kids=0,full=false;
    for(let x=gx-1;x<=gx+1&&!full;x++)for(let y=gy-1;y<=gy+1&&!full;y++){
      if(x<0||x>=64||y<0||y>=64)continue;const l=cells.get(x*64+y);if(!l)continue;
      for(const j of l){if(seen.has(j))continue;seen.add(j);
        if(kids>=48){full=true;over.push([i,j]);break;}
        const L=pgLink(O[i],O[j]);if(L){C.push(i,j,L.fall,L.p1[0],L.p1[1],L.p1[2],L.p2[0],L.p2[1],L.p2[2]);kids++;}}}
  }
  return{o:O,f:F,c:C,over:over};
}

// ---- splines: sv_showcameras and g_showflypath -------------------------------------------
// The info_splinepath chains as SplinePath::CreatePath links them, a frame after the level
// starts, in spawn order: a node's "target" is its next (the first entity of that
// targetname), taken from any node that named the same one before.
let SPLINES=null;
function splineGraph(){
  if(SPLINES)return SPLINES;
  const node=new Map();
  MAP.ents.forEach((e,ei)=>{if(e.cls==='info_splinepath'&&ENTS[ei].origin)node.set(ei,{ei:ei,next:-1,owner:-1});});
  for(const n of node.values()){const tg=gameKey(n.ei,'target');if(!tg)continue;
    const t=gameTn(tg)[0];if(t==null||!node.has(t))continue;
    const m=node.get(t);
    if(m.owner>=0&&m.owner!==n.ei)node.get(m.owner).next=-1;
    n.next=t;m.owner=n.ei;}
  return SPLINES={node:node};
}
// one path as Camera::CreatePath builds it from a node: its points to the end of the
// chain (or round to the start), and with SPLINE_LOOP the point a "loop" key goes back to
function splinePath(start,loop){
  const S=splineGraph(),pts=[],seen=new Set();let lcp=0,n=start;
  while(n>=0&&S.node.has(n)&&!seen.has(n)){seen.add(n);const o=ENTS[n].origin;pts.push(o);
    const lk=gameKey(n,'loop'),lt=lk?gameTn(lk)[0]:null;
    if(loop&&lt!=null&&ENTS[lt]&&ENTS[lt].origin){const lo=ENTS[lt].origin,i=pts.findIndex(p=>p[0]===lo[0]&&p[1]===lo[1]&&p[2]===lo[2]);if(i>=0)lcp=i;}
    n=S.node.get(n).next;}
  return{pts:pts,loop:!!loop,lcp:lcp,ring:n===start};
}
// The paths drawn: each func_camera's from its target (SPLINE_LOOP with ORBIT, 1), then
// every chain no camera starts, from its first node (a ring of nodes as a loop)
function splinePaths(){
  const S=splineGraph(),out=[],from=new Set();
  for(let ei=1;ei<MAP.ents.length;ei++){const e=MAP.ents[ei];if(e.cls!=='func_camera')continue;
    const tg=gameKey(ei,'target'),t=tg?gameTn(tg)[0]:null;
    if(t==null||!S.node.has(t))continue;
    out.push(splinePath(t,(parseInt(e.kvl.spawnflags||'0',10)|0)&1));from.add(t);}
  for(const n of S.node.values())if(n.owner<0&&!from.has(n.ei))out.push(splinePath(n.ei,false));
  // rings: nodes no walk reached
  const seen=new Set();for(const P of out)P.pts.forEach(p=>seen.add(p));
  for(const n of S.node.values())if(!seen.has(ENTS[n.ei].origin)){const P=splinePath(n.ei,true);P.pts.forEach(p=>seen.add(p));out.push(P);}
  return out.filter(P=>P.pts.length);
}
// BSpline::Eval: a uniform cubic B-spline; SPLINE_CLAMP holds the ends, SPLINE_LOOP wraps
// back to its loop point (and is clamped before 0)
function bsplineAt(P,u,loop,lcp){
  const n=P.length,seg=Math.floor(u),t=u-seg,t2=t*t,t3=t2*t,m=1-t;
  const B=[m*m*m/6,(3*t3-6*t2+4)/6,(-3*t3+3*t2+3*t+1)/6,t3/6],r=[0,0,0];
  let j=loop&&u>=0?((seg%n)+n)%n:seg;
  for(let i=0;i<4;i++,j++){
    let k=j;
    if(loop&&u>=0){if(j>=n){j-=n-lcp;k=j;}}
    else k=Math.max(0,Math.min(n-1,j));
    for(let a=0;a<3;a++)r[a]+=P[k][a]*B[i];}
  return r;}
function dlSplines(cams,fly){
  const paths=splinePaths();
  // DrawCurve(10): from u = -2 to the number of points, a tenth at a time, in yellow
  if(cams)for(const P of paths){let prev=null;
    for(let u=Math.fround(-2);u<=P.pts.length;u=Math.fround(u+Math.fround(0.1))){const p=bsplineAt(P.pts,u,P.loop,P.lcp);if(prev)dl(prev,p,DC.yellow);prev=p;}}
  // a fly path: a 64-unit box on each node and the way between them
  if(fly)for(const P of paths)P.pts.forEach((p,i)=>{dlBox8(boxPts(p,[-32,-32,-32],[32,32,32],null),DC.cyan);
    if(i+1<P.pts.length)dl(p,P.pts[i+1],DC.green);});
  // a small wire camera where the game puts func_camera.tik (not in the game's paks)
  if(cams)for(let ei=1;ei<MAP.ents.length;ei++){const e=MAP.ents[ei];if(e.cls!=='func_camera'||!ENTS[ei].origin)continue;
    const ax=anglesAxis(entAngles(e.kvl)),o=ENTS[ei].origin;dlBox8(boxPts(o,[-12,-6,-8],[6,6,8],ax),DC.yellow);
    const at=(x,y,z)=>[o[0]+ax[0][0]*x+ax[1][0]*y+ax[2][0]*z,o[1]+ax[0][1]*x+ax[1][1]*y+ax[2][1]*z,o[2]+ax[0][2]*x+ax[1][2]*y+ax[2][2]*z];
    const l=at(6,0,0),C=[[16,8,6],[16,-8,6],[16,-8,-6],[16,8,-6]];
    C.forEach((c,i)=>{dl(l,at(...c),DC.yellow);dl(at(...c),at(...C[(i+1)%4]),DC.yellow);});}
}

// ---- cg_rain_drawcoverage ------------------------------------------------------------------
// CG_Rain: a func_rain's box, cut to rain_min_dist round the player across; the red
// rectangle at its bottom is where its drops land
function dlRain(feet){
  const md=+CVARS.cg_rain_min_dist||0;
  for(const[mn,mx]of wxVolumes()){
    const lo=[Math.max(mn[0],feet[0]-md),Math.max(mn[1],feet[1]-md)];
    const hi=[Math.min(mx[0],feet[0]+md),Math.min(mx[1],feet[1]+md)];
    if(lo[0]>hi[0]||lo[1]>hi[1])continue;
    const z=mn[2],C=[[lo[0],lo[1],z],[hi[0],lo[1],z],[hi[0],hi[1],z],[lo[0],hi[1],z]];
    for(let i=0;i<4;i++)dl(C[i],C[(i+1)%4],DC.red);}}

// ---- r_showstaticbboxes ----------------------------------------------------------------------
// R_AddStaticModelSurfaces: each static model the game draws gets its .tik's bounds times
// its scale, turned with it, every edge magenta (R_DebugRotatedBBox)
function dlStaticBoxes(){
  const G=GV,fs=D.bsp&&D.bsp.firstStatic!=null?D.bsp.firstStatic:MAP.ents.length,f=camAxes().f,fe=vdot(f,cam.pos);
  for(let ei=fs;ei<MAP.nMap;ei++){const X=ENTS[ei];if(X.model<0||!X.origin)continue;
    if(G.stM[ei-fs]!==G.frame)continue;          // not in a leaf the game draws
    const M=D.models[X.model],k=MAP.ents[ei].kvl,sc=parseFloat(k.scale)||1,tb=M.tb||[[-4,-4,-4],[4,4,4]];
    const P=boxPts(X.origin,tb[0].map(v=>v*sc),tb[1].map(v=>v*sc),anglesAxis(entAngles(k)));
    if(G.farBoxes){const b=ptsBounds(P);if(gvBeyond(f,fe,G.far,b.mins[0],b.mins[1],b.mins[2],b.maxs[0],b.maxs[1],b.maxs[2]))continue;}
    for(const[a,b]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]])dl(P[a],P[b],DC.magenta);}}

// ---- the lines, drawn -------------------------------------------------------------------------
let PDL=null;
function cvarLinesWanted(){
  return !!(CVARS.sv_showentnums||CVARS.sv_showbboxes||CVARS.g_entinfo||(routesOk()&&(CVARS.ai_shownodenums||CVARS.ai_shownode))||
    CVARS.sv_showcameras||CVARS.g_showflypath||CVARS.cg_rain_drawcoverage||(CVARS.r_showstaticbboxes&&GV));}
// the server's view of the camera (which entities it sends), kept up to date for these
function gvCamera(){if(GV)gvMark(GV,gvPointLeaf(GV,cam.pos));}
function drawCvarLines(vp){
  DL=[];ENTTEXT=[];
  if(!cvarLinesWanted()||!gl)return;
  const feet=feetPos();
  gvCamera();
  if(CVARS.sv_showentnums)dlEntNums(feet);
  if(CVARS.sv_showbboxes)dlBoxes(CVARS.sv_showbboxes,feet);
  if(CVARS.g_entinfo)dlEntInfo(CVARS.g_entinfo,feet);
  if(routesOk()&&PA()){if(CVARS.ai_shownode>0)dlNodes(feet);if(CVARS.ai_shownodenums)dlNodeNums(feet);}
  if(CVARS.sv_showcameras||CVARS.g_showflypath)dlSplines(CVARS.sv_showcameras,CVARS.g_showflypath);
  if(CVARS.cg_rain_drawcoverage)dlRain(feet);
  if(CVARS.r_showstaticbboxes&&GV){gvGL();gvUpdate();dlStaticBoxes();}
  if(DL.length){
    if(!PDL)PDL=compile(VS_GVL,FS_LINE);
    if(!B.dlBuf){B.dlBuf=gl.createBuffer();B.vDl=gvLineVAO(B.dlBuf,true);gl.bindVertexArray(null);}
    gl.bindBuffer(gl.ARRAY_BUFFER,B.dlBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(DL),gl.STREAM_DRAW);
    gvUniforms(PDL,vp,0.0015);
    gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);
    gl.bindVertexArray(B.vDl);gl.drawArrays(gl.LINES,0,DL.length/10);
    gl.bindVertexArray(null);gl.depthMask(true);
  }
  if(ENTTEXT.length)drawWorldText(vp,ENTTEXT);
}

// ---- floating text (G_DebugString, R_DrawFloatingString) --------------------------------------
// The game writes these in the world in verdana-14, 14 units tall, from their spot to the
// right along the view, hidden behind walls like the rest of the scene.
let PTXT=null;
const TXT_PX=28;                                 // canvas pixels per 14 units
function drawWorldText(vp,list){
  if(!PTXT)PTXT=compile(`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV; uniform mat4 uVP; out vec2 vUV;
void main(){vUV=aUV;gl_Position=uVP*vec4(aPos,1.0);}`,`#version 300 es
precision mediump float; in vec2 vUV; uniform sampler2D uTex; out vec4 o;
void main(){vec4 t=texture(uTex,vUV);if(t.a<0.02)discard;o=vec4(1.0,1.0,1.0,t.a);}`);
  // every string on one canvas, a row each, redrawn when the strings change
  const key=list.map(t=>t.s).join('\n'),RH=TXT_PX+6;
  if(!B.txt||B.txt.key!==key){
    const cv=document.createElement('canvas'),c2=cv.getContext('2d'),font=TXT_PX+'px Verdana,Tahoma,sans-serif';
    c2.font=font;const ws=list.map(t=>Math.ceil(c2.measureText(t.s).width)+4);
    cv.width=Math.min(4096,Math.max(4,...ws));cv.height=Math.min(4096,Math.max(4,list.length*RH));
    c2.font=font;c2.textBaseline='bottom';c2.fillStyle='#fff';
    list.forEach((t,i)=>c2.fillText(t.s,2,(i+1)*RH-3));
    if(!B.txt)B.txt={tex:gl.createTexture()};
    gl.bindTexture(gl.TEXTURE_2D,B.txt.tex);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,cv);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    B.txt.key=key;B.txt.w=cv.width;B.txt.h=cv.height;B.txt.ws=ws;}
  const a=camAxes(),u=TXT_PX/14,V=[];
  list.forEach((t,i)=>{if((i+1)*RH>B.txt.h)return;
    const w=Math.min(B.txt.ws[i],B.txt.w)/u,h=RH/u,p=t.p,r=a.r,q=a.u;
    const v0=(i*RH)/B.txt.h,v1=((i+1)*RH)/B.txt.h,u1=Math.min(B.txt.ws[i],B.txt.w)/B.txt.w;
    const P=(x,y)=>[p[0]+r[0]*x+q[0]*y,p[1]+r[1]*x+q[1]*y,p[2]+r[2]*x+q[2]*y];
    const c=[[P(0,0),0,v1],[P(w,0),u1,v1],[P(w,h),u1,v0],[P(0,h),0,v0]];
    for(const k of[0,1,2,0,2,3])V.push(c[k][0][0],c[k][0][1],c[k][0][2],c[k][1],c[k][2]);});
  if(!V.length)return;
  if(!B.txtBuf){B.txtBuf=gl.createBuffer();B.vTxt=gl.createVertexArray();gl.bindVertexArray(B.vTxt);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.txtBuf);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,20,0);
    gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,2,gl.FLOAT,false,20,12);gl.bindVertexArray(null);}
  gl.bindBuffer(gl.ARRAY_BUFFER,B.txtBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(V),gl.STREAM_DRAW);
  gl.useProgram(PTXT);gl.uniformMatrix4fv(PTXT.u.uVP,false,vp);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,B.txt.tex);gl.uniform1i(PTXT.u.uTex,0);
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);gl.disable(gl.CULL_FACE);
  gl.bindVertexArray(B.vTxt);gl.drawArrays(gl.TRIANGLES,0,V.length/5);
  gl.bindVertexArray(null);gl.depthMask(true);gl.disable(gl.BLEND);
}

// ---- r_light_showgrid ---------------------------------------------------------------------------
// R_AddLightGridSurfacesToScene: a 4 x 4 square (the "showgrid" shader turns it to face the
// view: autosprite) on every light grid point within 256 units of the eye, in the colour
// R_GetLightingGridValueFast finds there (the nearest lit sample, its palette colour).
let LGRID=null;
function lightGrid(){
  if(LGRID!==null)return LGRID;
  const g=D.lg;if(!g){LGRID=false;return false;}
  return LGRID={m:g.m,s:g.s,b:g.b,o:D.bytes(g.o),p:D.bytes(g.p),d:D.bytes(g.d)};
}
const LG_SEARCH=[[0,4,2,6,1,5,3,7],[0,2,4,6,1,3,5,7],[0,0,0,0,0,0,0,0],[0,2,1,3,4,6,5,7],[0,4,1,5,2,6,3,7],[0,0,0,0,0,0,0,0],[0,1,4,5,2,3,6,7],[0,1,2,3,4,5,6,7]];
function lgOff(G,i){return G.o[i*2]|(G.o[i*2+1]<<8);}
function lgFast(G,pos){
  const gp=[0,0,0],fd=[0,0,0];let tog=0,ord=0;
  for(let i=0;i<3;i++){let v=(G.s[i]*0.5+pos[i]-G.m[i])/G.s[i];gp[i]=Math.floor(v);v-=gp[i];
    if(gp[i]<0){gp[i]=0;v=0;}else if(gp[i]>G.b[i]-2){gp[i]=G.b[i]-2;v=1;}
    fd[i]=0.5-v;if(fd[i]<0){fd[i]=-fd[i];tog|=1<<i;}}
  if(fd[1]>=fd[0])ord=1;if(fd[2]>=fd[0])ord|=2;if(fd[2]>=fd[1])ord|=4;
  const smp=[-1,-1,-1,-1,-1,-1,-1,-1],step=G.b[1],base=gp[1]+G.b[0]+gp[0]*G.b[1],D8=G.d,sb=v=>v>127?v-256:v;
  for(let i=0;i<8;i++){
    const j=LG_SEARCH[ord][i]^tog;
    if(smp[j]<0){
      let at;
      switch(j&3){case 0:at=lgOff(G,gp[0])*256+lgOff(G,base);break;case 1:at=lgOff(G,gp[0])*256+lgOff(G,base+1);break;
        case 2:at=lgOff(G,gp[0]+1)*256+lgOff(G,base+step);break;default:at=lgOff(G,gp[0]+1)*256+lgOff(G,base+step+1);}
      const k=j&~1;let row=gp[2],d=0,len=0;
      for(let guard=0;guard<4096;guard++){
        let done=false;
        for(;sb(D8[at+d])>=0;d+=2,row-=len){len=sb(D8[at+d])+2;
          if(len-1<row)continue;
          if(len-1>row){smp[k+1]=smp[k]=D8[at+d+1];}else{smp[k]=D8[at+d+1];smp[k+1]=D8[at+d+3];}
          done=true;break;}
        if(done)break;
        const n=-sb(D8[at+d]);
        if(n>row){smp[k]=D8[at+row+d+1];smp[k+1]=(n-1===row)?D8[at+row+d+3]:D8[at+row+d+2];break;}
        row-=n;d+=n+1;
      }
    }
    if(smp[j]>0){const c=smp[j]*3;return[G.p[c],G.p[c+1],G.p[c+2]];}
  }
  return[255,255,255];                         // tr.identityLightByte
}
function drawLightGrid(vp){
  const G=lightGrid();if(!G||!gl)return;
  const e=cam.pos,mn=[0,0,0],mx=[0,0,0];
  for(let i=0;i<3;i++){mn[i]=G.m[i]+Math.floor((e[i]-256-G.m[i])/G.s[i])*G.s[i];mx[i]=G.m[i]+Math.floor((e[i]+256-G.m[i])/G.s[i])*G.s[i];}
  const a=camAxes(),r=[a.r[0]*2,a.r[1]*2,a.r[2]*2],u=[a.u[0]*2,a.u[1]*2,a.u[2]*2],V=[];
  for(let z=mn[2];z<mx[2];z+=G.s[2])for(let y=mn[1];y<mx[1];y+=G.s[1])for(let x=mn[0];x<mx[0];x+=G.s[0]){
    const c=lgFast(G,[x,y,z]),q=k=>[x+r[0]*k[0]+u[0]*k[1],y+r[1]*k[0]+u[1]*k[1],z+r[2]*k[0]+u[2]*k[1]];
    const P=[q([-1,-1]),q([1,-1]),q([1,1]),q([-1,1])];
    for(const k of[0,1,2,0,2,3])V.push(P[k][0],P[k][1],P[k][2],c[0]/255,c[1]/255,c[2]/255,1);}
  LGRID.n=V.length/42;
  if(!V.length)return;
  if(!B.lgBuf){B.lgBuf=gl.createBuffer();B.vLg=gl.createVertexArray();gl.bindVertexArray(B.vLg);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.lgBuf);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,28,0);
    gl.enableVertexAttribArray(7);gl.vertexAttribPointer(7,4,gl.FLOAT,false,28,12);gl.bindVertexArray(null);}
  gl.bindBuffer(gl.ARRAY_BUFFER,B.lgBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(V),gl.STREAM_DRAW);
  setCommon(PC,vp,0);gl.uniform1f(PC.u.uShade,0);gl.uniform1i(PC.u.uUseTex,0);gl.uniform3f(PC.u.uFlat,1,1,1);gl.uniform3f(PC.u.uFog,0,1,0);
  gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);
  gl.bindVertexArray(B.vLg);gl.vertexAttrib1f(2,0);gl.drawArrays(gl.TRIANGLES,0,V.length/7);gl.bindVertexArray(null);
}

// ---- r_showsky ------------------------------------------------------------------------------------
// RB_StageIteratorSky: the sky polygons the game draws from here are clipped to the six sides
// of a box round the eye (ClipSkyPolygon), each side's covered part is rounded out to
// quarters (DrawSkyBox) and those blocks of the sky box are what it draws; r_showsky draws
// them with the depth range squeezed to the near end, in front of everything.
const SKY_CLIP=[[1,1,0],[1,-1,0],[0,-1,1],[0,1,1],[1,0,1],[-1,0,1]];
const SKY_VTS=[[-2,3,1],[2,3,-1],[1,3,2],[-1,3,-2],[-2,-1,3],[-2,1,-3]];
const SKY_STV=[[3,-1,2],[-3,1,2],[1,3,2],[-1,-3,2],[-2,-1,3],[2,-1,-3]];
function skyAddPoly(S,vs){
  const v=[0,0,0];for(const p of vs){v[0]+=p[0];v[1]+=p[1];v[2]+=p[2];}
  const av=v.map(Math.abs);let axis;
  if(av[0]>av[1]&&av[0]>av[2])axis=v[0]<0?1:0;else if(av[1]>av[2]&&av[1]>av[0])axis=v[1]<0?3:2;else axis=v[2]<0?5:4;
  const g=(p,j)=>j<0?-p[-j-1]:p[j-1];
  for(const p of vs){const dv=g(p,SKY_VTS[axis][2]);if(dv<0.001)continue;
    const s=g(p,SKY_VTS[axis][0])/dv,t=g(p,SKY_VTS[axis][1])/dv;
    if(s<S.mn[0][axis])S.mn[0][axis]=s;if(t<S.mn[1][axis])S.mn[1][axis]=t;
    if(s>S.mx[0][axis])S.mx[0][axis]=s;if(t>S.mx[1][axis])S.mx[1][axis]=t;}}
function skyClip(S,vs,stage){
  if(stage===6){skyAddPoly(S,vs);return;}
  const n=SKY_CLIP[stage],d=vs.map(p=>p[0]*n[0]+p[1]*n[1]+p[2]*n[2]),sd=d.map(x=>x>0.1?1:x<-0.1?2:0);
  if(!sd.includes(1)||!sd.includes(2)){skyClip(S,vs,stage+1);return;}
  const f=[],b=[];
  for(let i=0;i<vs.length;i++){const p=vs[i],j=(i+1)%vs.length;
    if(sd[i]!==2)f.push(p);if(sd[i]!==1)b.push(p);
    if(sd[i]===0||sd[j]===0||sd[j]===sd[i])continue;
    const t=d[i]/(d[i]-d[j]),q=vs[j],c=[p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1]),p[2]+t*(q[2]-p[2])];
    f.push(c);b.push(c);}
  skyClip(S,f,stage+1);skyClip(S,b,stage+1);}
function skyVec(s,t,axis,size){const b=[s*size,t*size,size],o=[0,0,0];
  for(let j=0;j<3;j++){const k=SKY_STV[axis][j];o[j]=k<0?-b[-k-1]:b[k-1];}return o;}
function drawShowSky(vp){
  if(!CVARS.r_showsky||!GV||!gl||!GV.sk||!GV.sk.length)return;
  gvGL();gvUpdate();
  const G=GV,e=cam.pos,byTex=new Map(),a=camAxes(),tx=Math.tan(fovX*Math.PI/360),ty=tx*H/W;
  // the view's four side planes (the game adds only what is in the view)
  const fr=[[tx*a.f[0]-a.r[0],tx*a.f[1]-a.r[1],tx*a.f[2]-a.r[2]],[tx*a.f[0]+a.r[0],tx*a.f[1]+a.r[1],tx*a.f[2]+a.r[2]],
            [ty*a.f[0]-a.u[0],ty*a.f[1]-a.u[1],ty*a.f[2]-a.u[2]],[ty*a.f[0]+a.u[0],ty*a.f[1]+a.u[1],ty*a.f[2]+a.u[2]]];
  let nTri=0;
  for(const s of G.skyNow||[]){const o=s*8,ti=G.si[o+5];let S=byTex.get(ti);
    if(!S){S={mn:[[9999,9999,9999,9999,9999,9999],[9999,9999,9999,9999,9999,9999]],mx:[[-9999,-9999,-9999,-9999,-9999,-9999],[-9999,-9999,-9999,-9999,-9999,-9999]]};byTex.set(ti,S);}
    const K=G.sk,P=G.v;
    for(let k=G.si[o+3];k+2<G.si[o+3]+G.si[o+4];k+=3){
      const tri=[0,1,2].map(m=>{const v=K[k+m]*3;return[P[v]-e[0],P[v+1]-e[1],P[v+2]-e[2]];});
      if(fr.some(n=>tri.every(p=>p[0]*n[0]+p[1]*n[1]+p[2]*n[2]<0)))continue;
      skyClip(S,tri,0);nTri++;}}
  G.skyTris=nTri;G.skyBlocks=0;
  if(!nTri)return;
  const fogged=fogOn(),flat=fogged?fogCol():skyColour(),T=(performance.now()-T0)/1000,size=farPlane()/1.75;
  if(!B.skBuf){B.skBuf=gl.createBuffer();B.vSk=gl.createVertexArray();gl.bindVertexArray(B.vSk);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.skBuf);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,12,0);gl.bindVertexArray(null);}
  gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);gl.disable(gl.DEPTH_TEST);gl.depthMask(false);
  let blocks=0;
  for(const[ti,S]of byTex){
    const V=[];
    for(let i=0;i<6;i++){
      const lo=[Math.floor(S.mn[0][i]*4)/4,Math.floor(S.mn[1][i]*4)/4],hi=[Math.ceil(S.mx[0][i]*4)/4,Math.ceil(S.mx[1][i]*4)/4];
      if(lo[0]>=hi[0]||lo[1]>=hi[1])continue;
      const c=x=>Math.max(-1,Math.min(1,x)),s0=c(lo[0]),t0=c(lo[1]),s1=c(hi[0]),t1=c(hi[1]);
      blocks+=Math.round((s1-s0)*4)*Math.round((t1-t0)*4);
      const q=[skyVec(s0,t0,i,size),skyVec(s1,t0,i,size),skyVec(s1,t1,i,size),skyVec(s0,t1,i,size)];
      for(const k of[0,1,2,0,2,3])V.push(q[k][0]+e[0],q[k][1]+e[1],q[k][2]+e[2]);}
    if(!V.length)continue;
    gl.bindBuffer(gl.ARRAY_BUFFER,B.skBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(V),gl.STREAM_DRAW);
    const te=TEX[ti]||{},sb=te.sb,t=(!fogged&&sb!=null)?B.skyTex[sb]:null,C=(!fogged&&te.cl!=null)?CLOUDS[te.cl]:null,list=cloudLayers(C),Q=skyProgram(list.length);
    gl.useProgram(Q);gl.uniformMatrix4fv(Q.u.uVP,false,vp);gl.uniform3fv(Q.u.uEye,cam.pos);gl.uniform1f(Q.u.uClip,0);
    gl.uniform1i(Q.u.uSky,2);gl.uniform3fv(Q.u.uSkyCol,flat);for(let k=0;k<4;k++)if(Q.u['uC'+k])gl.uniform1i(Q.u['uC'+k],4+k);
    if(Q.u.uPush)gl.uniform1f(Q.u.uPush,0);
    if(Q.u.uTm){gl.uniform2f(Q.u.uTm,1,1);gl.uniform1i(Q.u.uAg,0);}
    gl.activeTexture(gl.TEXTURE2);gl.bindTexture(gl.TEXTURE_2D_ARRAY,t||B.skyNone);gl.activeTexture(gl.TEXTURE0);
    gl.uniform1i(Q.u.uHasBox,t?1:0);if(list.length)setClouds(Q,C,list,T);
    gl.bindVertexArray(B.vSk);gl.drawArrays(gl.TRIANGLES,0,V.length/3);}
  G.skyBlocks=blocks;
  gl.bindVertexArray(null);gl.enable(gl.DEPTH_TEST);gl.depthMask(true);
}

// ============================================================================
//  Game cvars: the list under Display (or `, as the game's console key)
// ============================================================================
// Some of the game's debugging cvars, doing in the page what they do in game, and the
// game settings some of them depend on. CVARS holds their values; a click on a row sets
// it (or back to its default), and the filter box takes a cvar and a value the way the
// game's console does: "r_showtris 2", Enter.
const CVAR_DEFAULTS={r_showtris:0,r_shownormals:0,r_lockpvs:0,r_novis:0,cm_noAreas:0,r_showsky:0,r_showstaticbboxes:0,
  r_farplane:0,r_farplane_color:'.5 .5 .5',r_farplane_nocull:0,r_farplane_nofog:0,r_lightmap:0,r_light_showgrid:0,
  sv_showentnums:0,sv_showbboxes:0,g_entinfo:0,g_entinfo_max:2048,sv_showcameras:0,g_showflypath:0,cg_rain_drawcoverage:0,
  ai_showroutes:0,ai_showroutes_distance:8200,ai_fallheight:96,ai_shownodenums:0,ai_shownode:0,ai_showallnode:0,g_nodecheck:0,
  g_gametype:0,skill:1,developer:0,sv_maxclients:1,
  cg_rain:0,cg_weather:'map',cg_rain_density:0,cg_rain_speed:2048,cg_rain_speed_vary:512,cg_rain_slant:50,cg_rain_length:90,
  cg_rain_width:1,cg_rain_min_dist:512,cg_rain_shader:'textures/rain',cg_rain_numshaders:0,vss_wind_x:8,vss_wind_y:4,
  com_maxfps:85,com_target_game:0,cg_rain_wholemap:0,cg_thunder:0,
  r_static_shadermultiplier0:1,r_static_shadermultiplier1:1,r_static_shadermultiplier2:1,r_static_shadermultiplier3:1};
const CVARS=Object.assign({},CVAR_DEFAULTS);
// a lock is of where the camera was, and the weather is the map's (its script's) unless
// changed while it is open: not kept for next time
const CVAR_NOSAVE=new Set(['r_lockpvs','cg_weather','cg_rain_density','cg_rain_speed','cg_rain_speed_vary','cg_rain_slant',
  'cg_rain_length','cg_rain_width','cg_rain_min_dist','cg_rain_shader','cg_rain_numshaders','cg_rain_wholemap','r_static_shadermultiplier1']);
// the values a cvar without a number box takes (the rest are switches, 0 or 1)
const CVAR_RANGE={r_showtris:[0,3],r_lightmap:[0,2],sv_showbboxes:[-28,128],g_entinfo:[0,4],com_target_game:[0,2]};
// the cvars the viewer starts at another value than the game does: the game's (the console says so)
const CVAR_GAMEDEF={ai_showroutes_distance:1000,cg_rain:1};
const CVAR_ROWS=[
 {h:'Render distance: farplane fog and culling'},
 {n:'r_farplane',num:[0,65536],step:64,f:1,d:'units, for the map\'s',
  t:'Fog and cull at this distance in place of the map\'s farplane (0: the map\'s own), in the colour r_farplane_color, culling what r_farplane_nocull says. The game always draws a farplane\'s fog, so this turns the fog on here'},
 {n:'r_farplane_color',str:1,need:'farset',d:'r g b, 0 to 1',
  t:'The fog colour of r_farplane, red green blue from 0 to 1 (the game\'s default .5 .5 .5)'},
 {n:'r_farplane_nocull',num:[-1,1],need:'farset',d:'1 none, -1 sky',
  t:'What r_farplane culls: 0 (the default) the BSP nodes and the models past it, 1 nothing, -1 the models only (as for a portal sky). r_showtris shows it'},
 {n:'r_farplane_nofog',v:1,need:'fog',d:'no fog',
  t:'Don\'t draw the farplane\'s fog, the map\'s or r_farplane\'s (what is past the farplane is still culled: r_showtris shows it)'},
 {h:'What the renderer draws'},
 {n:'r_showtris',v:1,need:'vis',d:'outline what the game draws',
  t:'Outline every triangle the game draws from where the camera is, hidden behind walls: what is in the camera\'s PVS and in an area joined to its own, without the faces turned away from it'},
 {n:'r_showtris',v:2,need:'vis',d:'through walls: the culling',
  t:'The same outlines drawn through walls, with an axis cross at each model the game draws: shows what it culls from here. Step out of a room and the rest of the map comes in as soon as the camera reaches a cluster that can see it'},
 {n:'r_showtris',v:3,need:'vis',d:'axis crosses only',
  t:'Only the axis crosses: at the world origin, and at the origin of each brush entity and model the game draws from here (red up, green along y, blue a diagonal, as the engine draws it)'},
 {n:'r_shownormals',v:1,need:'nrm',d:'vertex normals',
  t:'A white line 2 units long along the normal at each vertex the game draws from here, over everything (DrawNormals, tr_shade.c): a face\'s plane, a curve\'s grid (MakeMeshNormals), a model\'s vertices turned by their bones; a static prop\'s lines grow with its scale. Terrain has none: the renderer never makes normals for it. In game a face or curve only fills its normals in when its shader uses them (an environment map, deformVertexes, a dot alphaGen or rgbGen...) or a dynamic light is in the scene; otherwise its lines show whatever the surface before it left, pointing anywhere. Here every face and curve shows its own. In game it also takes developer 1'},
 {n:'r_lockpvs',v:1,need:'vis',d:'freeze what is drawn',
  t:'Keep the leafs the renderer marked from where the camera is now (R_MarkLeaves stops): fly out with r_showtris 2 to see the whole of what the game draws from that spot. The entities still follow the camera, as the server sends them from where the player is'},
 {n:'r_novis',v:1,need:'vis',d:'ignore the PVS',
  t:'Ignore the visibility data and the doors: the renderer keeps every leaf (R_MarkLeaves marks them all). Compare with r_showtris 2: only the farplane and the faces turned away are left out'},
 {n:'cm_noAreas',v:1,need:'vis',d:'every door open',
  t:'Count every area portal as open, as if every door were open, for r_showtris. Off: the game\'s start, with every door shut but those that start open, so the areas behind a shut door aren\'t drawn even when they are in the PVS'},
 {n:'r_showsky',v:1,need:'sky',d:'the sky drawn from here',
  t:'Draw the parts of the sky box the game draws from here in front of everything: the sky polygons in view are projected onto the six sides of a box round the eye and rounded out to quarters of a side (tr_sky.c). In game the walls are drawn after the sky and still cover it, unless the sky has a solid cloud layer'},
 {n:'r_showstaticbboxes',v:1,need:'vis',d:'static models\' boxes',
  t:'A magenta box round each static model the game draws from here (the leafs it keeps and the farplane decide): its .tik\'s bounds times its scale, turned with it'},
 {h:'Lighting'},
 {n:'r_lightmap',v:1,need:'lit',d:'lightmaps only',
  t:'Lightmapped surfaces show their lightmap in place of their texture (the texture\'s alpha still cuts or blends it): the game draws a surface\'s stages only as far as its lightmap stage, and a stage joined with the texture replaces the colour. A shader that multiplies the lightmap over its texture in a pass of its own keeps the texture, as in game'},
 {n:'r_lightmap',v:2,need:'lit',d:'lightmap brightness',
  t:'The lightmaps coloured by how bright their raw bytes are, as the game makes them when the map loads (tr_bsp.c): red for dark, then yellow, green, cyan and blue to magenta for the brightest; the brightest value it prints is under the list. In game it takes a vid_restart'},
 {n:'r_light_showgrid',v:1,need:'lgrid',d:'light grid points',
  t:'A small square on each point of the light grid within 256 units of the camera, in the colour the grid gives there (R_GetLightingGridValueFast): the light the game\'s models take'},
 {h:'Entities'},
 {n:'sv_showentnums',v:1,d:'entity numbers',
  t:'Each entity\'s number (the one script errors give) in yellow over it, within 1000 units of the player: the world 1022, then every map entity from sv_maxclients up, in the order the game spawns them. Path nodes, player starts and other simple entities have none; g_gametype, skill and developer below decide which entities spawn'},
 {n:'sv_showbboxes',v:1,d:'solid entities',
  t:'Within 1000 units of the player, a yellow box round each solid entity, turned with it (its uprights blue). Solid as each class sets itself up when the level starts; a script can change it. The box is its "setsize" key, else its .tik\'s setsize, else its .tik\'s bounds times its scale; an AI gives itself a standing player\'s box as it starts, ( -15 -15 0 ) ( 15 15 94 ) (Actor::EventStart)'},
 {n:'sv_showbboxes',v:2,d:'solid ones, world-aligned',
  t:'The magenta box the server links each solid entity with: the bounds of its turned box, a unit bigger all round'},
 {n:'sv_showbboxes',v:3,d:'entities with a model',
  t:'A yellow box round each entity that has a .tik model'},
 {n:'sv_showbboxes',v:4,d:'every entity',
  t:'A yellow box round every entity: a point entity without a model has no size, so its box is a point'},
 {n:'sv_showbboxes',v:7,d:'models\' .tik bounds',
  t:'A cyan box round each model: the bounds of its .tik\'s idle animation times its scale (TIKI_CalculateBounds), whatever its setsize'},
 {n:'sv_showbboxes',v:8,d:'models and origins',
  t:'A yellow box round each entity with a model and a small cyan box on its origin. (9 to 27 show the AI\'s hit spheres: see the Model Viewer)'},
 {n:'g_entinfo',v:1,d:'AI leash and distances',
  t:'What the game tells about the entity you look at (within 1024 units and 18° of the view; the AI within g_entinfo_max and 25°): its entity number, radnum, targetname and health over it, a door\'s state, an AI\'s think state. 1 adds an AI\'s green leash circle round its home and its mindist (red) and maxdist (blue) circles, from its keys or the game\'s defaults (512, 128, 1024)'},
 {n:'g_entinfo',v:2,d:'AI hearing and sight',
  t:'The same, with an AI\'s hearing (red) and sight (blue) circles in place of the others (2048 each unless its keys say)'},
 {n:'g_entinfo',v:3,d:'the text only',t:'The text alone, no circles'},
 {n:'g_entinfo',v:4,d:'AI text from anywhere',t:'The text alone, and an AI\'s whatever the direction and distance'},
 {n:'g_entinfo_max',num:[0,65536],step:64,d:'units',t:'How far away g_entinfo tells about an AI (the game\'s default is 2048)'},
 {n:'sv_showcameras',v:1,need:'spline',d:'cameras and their paths',
  t:'The cameras (a wire stand-in: func_camera.tik isn\'t in the game\'s files) and their spline paths in yellow: each func_camera\'s from its target (a loop with ORBIT), and every other info_splinepath chain. In game a path shows while a camera follows it'},
 {n:'g_showflypath',v:1,need:'spline',d:'fly paths',
  t:'The paths a script_object can fly along (flypath): a cyan box on each info_splinepath node and a green line to the next. In game they show while something flies them'},
 {h:'Weather: rain and snow (func_rain)'},
 {n:'cg_rain',v:1,d:'weather on',
  t:'The client\'s weather switch. The viewer starts with it off; the game\'s default is 1 (the Low graphics preset sets 0). Display > Weather (Y) is the same switch'},
 {n:'cg_thunder',v:1,d:'thunder on',
  t:'global/weather.scr\'s lightning, without its sound: every so many seconds one of its three flickers (the sky gone and the screen and fog flashed white, the $weatherF windows lit), at its own timings',
  ng:'This is not a real game cvar. In-game, thunder only runs on a map whose script runs global/weather.scr (m5l1a, m5l1b), every level.thundertime + a random 0 to 1.5 x level.thundertime seconds (level.thundertime = 20 at first, 6 at the middle of its storm); a map script changes it with level.thundertime = 20'},
 {n:'cg_weather',str:1,d:'snow, rain, blizzard … map',
  t:'Sets every cg_rain_ value below at once, as weather.scr does:\nsnow, snow_fast, blizzard, hail, snow_original (the game\'s m6l1a snow), rain, drizzle, monsoon, rain_original (the game\'s m5l1a rain), off, map, for the map script\'s values\n\nIt starts at "map" when the map (or its script) sets the weather, else at "rain", since "map" would make nothing fall',
  ng:'This is not a real game cvar. In-game, the values can only be changed in map script with level.rain_density = 0.2, level.rain_speed = 32 ... (weather.scr copies them from cvars of these names)'},
 {n:'cg_rain_density',num:[0,100],step:0.05,f:1,d:'drops a frame',
  t:'level.rain_density: each client frame, each rain box near you starts sqrt(width x depth) x density / 200 drops (in the square rain_min_dist round you), at most 4096',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_density = 0.2'},
 {n:'cg_rain_speed',num:[0,100000],step:16,f:1,d:'units a second',t:'level.rain_speed: how fast a drop falls',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_speed = 32'},
 {n:'cg_rain_speed_vary',num:[0,100000],step:16,d:'units a second',t:'level.rain_speed_vary: a random 0 to this much added to each drop\'s speed',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_speed_vary = 16'},
 {n:'cg_rain_slant',num:[0,100000],step:16,d:'units',t:'level.rain_slant: each drop lands a random 0 to this many units over in x and in y (both the same way: the rain leans toward +x +y), plus the wind',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_slant = 250'},
 {n:'cg_rain_length',num:[0,10000],step:1,f:1,d:'units',t:'level.rain_length: the length of a drop\'s streak (snow: the flake\'s size, with the width)',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_length = 2'},
 {n:'cg_rain_width',num:[0,1000],step:0.1,f:1,d:'units',t:'level.rain_width: half the width of a drop (the streak is twice this wide)',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_width = 1'},
 {n:'cg_rain_min_dist',num:[0,65536],step:64,f:1,d:'units round you',t:'level.rain_min_dist: drops start only this close to the viewer (across): the rest of a rain box stays dry. cg_rain_drawcoverage shows it',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_min_dist = 1800'},
 {n:'cg_rain_shader',str:1,d:'textures/rain, textures/snow0',
  t:'level.rain_shader: the drops\' shader. The game has:\ntextures/rain (a streak) and textures/snow0 to textures/snow11 (flakes: squares that face the camera)',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_shader = "textures/snow0"'},
 {n:'cg_rain_numshaders',num:[0,32],d:'0: just the shader',t:'level.rain_numshaders: with N, each box each frame takes one of the shader\'s name + 0 to N - 1 (a digit it ends with dropped: textures/snow0 and 12 give snow0 to snow11)',
  ng:'This is not a real game cvar. In-game, the value can only be changed in map script with level.rain_numshaders = 12'},
 {n:'vss_wind_x',num:[-100000,100000],step:1,f:1,d:'units',t:'The wind added to where every drop lands, in x (the game\'s default 8)',
  ng:'This cvar comes from OpenMoHAA: it doesn\'t exist in the original Allied Assault 1.11 game'},
 {n:'vss_wind_y',num:[-100000,100000],step:1,f:1,d:'units',t:'The wind in y (the game\'s default 4)',
  ng:'This cvar comes from OpenMoHAA: it doesn\'t exist in the original Allied Assault 1.11 game'},
 {n:'com_maxfps',num:[10,1000],d:'frames a second',
  t:'How many client frames a second the weather is made at (the game\'s default 85): each frame starts drops, so a faster client makes more rain, and runs out of beams sooner'},
 {n:'com_target_game',num:[0,2],d:'0 AA 1.11, 2 OpenMoHAA',
  t:'Which game\'s weather: 0 Allied Assault 1.11 (drops start at the top of the rain box and live as long as they take to fall), 1 Spearhead / 2 Breakthrough and OpenMoHAA (drops start anywhere in the box\'s height, 10 s at most, so tall boxes fill at once)',
  ng:'This cvar comes from OpenMoHAA: it doesn\'t exist in the original Allied Assault 1.11 game'},
 {n:'cg_rain_wholemap',v:1,d:'rain over the whole map',
  t:'The whole map\'s box counts as one more rain box, as a func_rain over the whole map would (what weather.scr\'s spawned volumes are for), so a map without one can be tried',
  ng:'This is not a real game cvar. In-game, weather can only fall in func_rain brushes (Rain in MOHRadiant), or in func_rain entities a map script spawns'},
 {n:'r_static_shadermultiplier1',num:[-100,100],step:0.1,f:1,d:'how far leaves sway',
  t:'Scales the amplitude of every static model\'s deformVertexes wave or flap: how far the trees\' leaves and the plants sway (the game\'s default 1, 0 stills them). global/weather.scr sets it each second to (raindensity + 1.5) / 2.5: 0.2 calm, 1.8 at the middle of its storm (where the viewer starts on its maps), 4.6 at the storm\'s height'},
 {n:'r_static_shadermultiplier0',num:[-100,100],step:0.1,f:1,d:'their base',t:'Scales the base of every static model\'s deformVertexes wave or flap (the game\'s default 1)'},
 {n:'r_static_shadermultiplier2',num:[-100,100],step:0.1,f:1,d:'their phase',t:'Scales the phase of every static model\'s deformVertexes wave or flap (the game\'s default 1)'},
 {n:'r_static_shadermultiplier3',num:[-100,100],step:0.1,f:1,d:'their speed',t:'Scales the frequency of every static model\'s deformVertexes wave or flap: how fast its leaves move (the game\'s default 1)'},
 {n:'cg_rain_drawcoverage',v:1,need:'rain',d:'where the rain lands',
  t:'A red rectangle at the bottom of each rain box the client gets, cut to cg_rain_min_dist round the player: where its drops land'},
 {h:'AI paths'},
 {n:'ai_showroutes',v:1,need:'paths',d:'AI path connections',
  t:'The connections the AI can walk between path nodes, from the map\'s .pth file: green both ways, a red arrowhead one way (pointing where it goes), a red X on a node with no connections, a blue circle on a node marked not to link. Only the nodes within ai_showroutes_distance of the camera'},
 {n:'ai_showroutes_distance',num:[0,65536],need:'paths',d:'units',
  t:'ai_showroutes and ai_shownodenums draw the nodes within this many units of the camera. The game\'s default is 1000; the viewer starts at 8200, so they show from far away: the page draws that many without slowing down'},
 {n:'ai_fallheight',num:[0,1024],need:'paths',d:'units',
  t:'ai_showroutes leaves out the connections with a drop higher than this, and a connection counts as both ways only when the way back drops less (the game\'s default is 96)'},
 {n:'ai_shownodenums',v:1,need:'paths',d:'node numbers',
  t:'Each path node\'s number in yellow over it, within ai_showroutes_distance of the camera'},
 {n:'ai_shownode',num:[0,4096],need:'paths',d:'nodes the AI finds here',
  t:'Up to this many path nodes the game finds for where you stand: the nodes of your 256-unit cell within 94 units of your height that a player-sized box can reach (traced here against the world\'s brushes), nearest first; if none can be reached, the nearest. Each is a 31 x 31 x 36 box in its type\'s colour (yellow corner left, lime corner right, cyan duck, red sniper, blue concealment, green cover, magenta plain, black flags that can\'t go together) with a white line toward its yaw. No node at all: a red circle round you'},
 {n:'ai_showallnode',v:1,need:'paths',d:'every node at your height',
  t:'ai_shownode shows every node within 94 units of your height, nearest first, however many it is set to'},
 {n:'g_nodecheck',v:1,need:'paths',d:'path node errors',
  t:'In game the path nodes are built again to show their errors, and the level stops with "Node check failed" when a node has 48 paths to check. Here: whether the build the map\'s .pth was saved from failed, and the nodes with 48 connections or more'},
 {h:'The game the entities spawn for'},
 {n:'g_gametype',num:[0,6],d:'0 single player',
  t:'Anything but 0 leaves out the entities flagged not for deathmatch (spawnflags 2048), which renumbers the rest (sv_showentnums, g_entinfo)'},
 {n:'skill',num:[0,3],d:'0 easy … 3 hard',
  t:'The difficulty: the entities flagged not for it (spawnflags 256 easy, 512 medium, 1024 hard) don\'t spawn (the game\'s default is 1)'},
 {n:'developer',v:1,d:'development entities',t:'Spawn the entities flagged for development (spawnflags 8192) too'},
 {n:'sv_maxclients',num:[1,64],d:'players',t:'The first entity numbers are the players\': the map\'s entities are numbered from this up (1 in single player)'}];
const CVAR_NAMES={};for(const k in CVAR_DEFAULTS)CVAR_NAMES[k.toLowerCase()]=k;
// each row's group header, for the filter
{let g=null;for(const r of CVAR_ROWS){if(r.h)g=r;else r.grp=g;}}
function cvarValRow(n){return CVAR_ROWS.find(r=>r.n===n&&(r.num||r.str));}
// what a row needs from the page, and why it can't be used without it
function cvarWhyNot(need){
  if(need==='vis'||need==='sky'||need==='nrm'){if(GV){if(need==='sky'&&!(GV.sk&&GV.sk.length))return 'this map has no sky polygons';
      if(need==='nrm'&&!GV.vn)return 'the build couldn\'t give this map its normals (see the Output pane)';return '';}
    return D.kind==='map'?'a .map has no PVS yet: open the compiled .bsp':'this .bsp has no BSP tree to walk';}
  if(need==='paths'){if(routesOk())return '';
    if(D.paths&&D.paths.err)return 'the path file '+(D.paths.src||'')+' can\'t be read: '+D.paths.err;
    if(!MAP.ents.some(e=>e.cls==='info_pathnode'&&!e.scr))return 'this map has no AI path nodes (info_pathnode), so the game makes no path file for it';
    return 'no path file for this map ('+String(D.path||'maps/?.bsp').replace(/\.(bsp|map)$/i,'.pth')+'): the game writes one when it first loads a map that has path nodes';}
  if(need==='lit'){if(!LIT)return D.kind==='map'?'a .map has no lightmaps: open the compiled .bsp':'this .bsp has no lightmaps (the game draws it at full brightness)';
    if(fullBright)return 'Full Brightness is on: turn it off (B) to see the game\'s lighting';return '';}
  if(need==='lgrid'){if(D.lg)return '';return D.kind==='map'?'a .map has no light grid: open the compiled .bsp':'this .bsp has no light grid';}
  if(need==='spline'){if(MAP.ents.some(e=>e.cls==='info_splinepath'||e.cls==='func_camera'))return '';return 'this map has no info_splinepath or func_camera';}
  if(need==='rain'){if(MAP.ents.some(e=>e.cls==='func_rain')||CVARS.cg_rain_wholemap||wxSkyBrushes().length)return '';return 'this map has no func_rain and no sky (cg_rain_wholemap 1 makes the whole map one)';}
  if(need==='farset'){if(Math.trunc(CVARS.r_farplane))return '';return 'only with r_farplane set';}
  if(need==='fog'){if(fogFar()>0)return '';return 'the map has no farplane (worldspawn "farplane") and r_farplane isn\'t set';}
  return '';
}
// a value as the cvar takes it: in its range, a whole number unless it takes fractions,
// the switches 0 or 1, a colour as text
function cvarClamp(n,v){
  const row=cvarValRow(n);
  if(row&&row.str){const s=String(v==null?'':v).trim();return s||null;}
  v=Number(v);if(!isFinite(v))return null;
  if(row)return Math.max(row.num[0],Math.min(row.num[1],row.f?v:Math.round(v)));
  const lim=CVAR_RANGE[n];if(lim)return Math.max(lim[0],Math.min(lim[1],Math.round(v)));
  return v?1:0;
}
function setCvar(name,val){
  const n=CVAR_NAMES[String(name).toLowerCase()];if(!n)return false;
  const v=cvarClamp(n,val);if(v==null)return false;
  if(n==='cg_weather'){if(!wxPreset(v))return false;}
  if(n==='ai_showroutes'&&!!v!==!!CVARS[n]){AIERR=!!v;TRACEPATH=!!v;}     // AI errors and Trace path follow AI routes
  CVARS[n]=v;
  if(n==='cg_rain_wholemap')WX.world=null;
  if(n.startsWith('cg_rain')||n==='cg_weather'||n==='ai_showroutes')syncButtons();
  if(n==='cg_thunder')thTick(performance.now());
  if(GV&&(n==='cm_noAreas'||n==='r_novis')){GV.key='';GV.skey='';}
  if(GV&&n==='r_lockpvs'){GV.key='';GV.marked=false;if(v)gvMark(GV,gvPointLeaf(GV,cam.pos));}
  if(GV&&(n==='r_farplane'||n==='r_farplane_nocull'))GV.dirty=true;
  if(n==='ai_fallheight'){ROUTES=null;if(MOD.ents.length)setTimeout(modRender,0);}
  if(n==='ai_shownode'||n==='ai_showallnode')NODELIST=null;
  // the Entities list follows the game the entities spawn for
  if(curTab==='ent'&&(n==='g_gametype'||n==='skill'||n==='developer'||n==='sv_maxclients'))renderList();
  saveOpts();cvarCountRender();cvarMenuRender();requestDraw();
  return true;
}
// the game cvars list's Reset button: every cvar that is set goes back to its default
function resetCvars(){
  const keys=cvarsSet();if(!keys.length)return;
  // cg_weather first: its "map" puts the cg_rain_ cvars back to the map's own, their defaults
  keys.sort((a,b)=>(b==='cg_weather')-(a==='cg_weather'));
  for(const k of keys)setCvar(k,CVAR_DEFAULTS[k]);
}
function cvarsSet(){return Object.keys(CVAR_DEFAULTS).filter(k=>String(CVARS[k])!==String(CVAR_DEFAULTS[k]));}
function cvarCountRender(){
  const el=$('cvarCount');if(!el)return;
  const on=cvarsSet();
  el.textContent=on.length?on.map(k=>k+' '+CVARS[k]).join(' · '):'none set';
  el.classList.toggle('on',on.length>0);
  el.title=on.length?on.map(k=>k+' '+CVARS[k]).join('\n'):'Every cvar in the list is at the game\'s default';
}
// ---- the list ------------------------------------------------------------------
let cvEl=null,cvBack=null,cvMsg='';
const CV_W=340,CV_GAP=6;
// the game cvars list closes when the window changes size (maximize, restore...), so it is
// never left stranded away from its button
window.addEventListener('resize',()=>{if(cvEl)cvarMenuClose();});
function cvarMenuClose(){
  if(cvEl){cvEl.remove();cvEl=null;}
  if(cvBack){cvBack.remove();cvBack=null;}
  cvMsg='';
  document.removeEventListener('keydown',cvarMenuKey,true);}
// Capture-phase while open: every key stays in the list (typing "1" in the filter mustn't
// switch Textures off). Esc or ` closes it; Enter runs what the filter box holds.
function cvarMenuKey(ev){
  const t=ev.target;
  if(ev.key==='Escape'||(ev.code==='Backquote'&&!ev.ctrlKey&&!ev.altKey&&!ev.metaKey)){
    cvarMenuClose();ev.preventDefault();ev.stopPropagation();return;}
  if(ev.key==='Enter'){
    if(t&&t.dataset&&t.dataset.cvar){setCvar(t.dataset.cvar,t.value);ev.preventDefault();}
    else if(t&&t.id==='cvSearch'){cvarConsole(t.value);ev.preventDefault();}
  }
  ev.stopPropagation();}
// The filter box as the game's console: "name value" sets it (a colour takes three
// words), "name" alone tells its value.
function cvarConsole(text){
  const w=String(text||'').trim().split(/\s+/).filter(Boolean);
  if(!w.length)return;
  const n=CVAR_NAMES[w[0].toLowerCase()];
  if(!n){
    const rows=cvarRowsFor(w[0]).filter(r=>!r.h);
    if(rows.length===1&&w.length===1){cvarRowClick(rows[0]);return;}
    cvMsg='Unknown cvar "'+w[0]+'": the list has '+Object.keys(CVAR_DEFAULTS).length+' (type part of a name to find one)';cvarMenuRender();return;}
  if(w.length===1){cvMsg='"'+n+'" is:"'+CVARS[n]+'" default:"'+CVAR_DEFAULTS[n]+'"'+
    (n in CVAR_GAMEDEF?' (the game\'s default is '+CVAR_GAMEDEF[n]+')':'');cvarMenuRender();return;}
  const val=typeof CVAR_DEFAULTS[n]==='string'?w.slice(1).join(' '):w[1];
  if(!setCvar(n,val)){cvMsg='"'+w[1]+'" isn\'t a number';cvarMenuRender();return;}
  // the reason a cvar can't work here is already the line under the message
  const why=cvarWhyNot((CVAR_ROWS.find(r=>r.n===n)||{}).need);
  cvMsg=n+' '+CVARS[n]+(why&&String(CVARS[n])!==String(CVAR_DEFAULTS[n])?' (no effect on this page: '+why+')':'');
  const s=$('cvSearch');if(s)s.value='';
  cvarMenuRender();
}
// the rows the filter keeps, each group's header with them
function cvarRowsFor(f){
  f=String(f||'').toLowerCase();
  const hit=r=>!f||(r.n+(r.num||r.str?'':' '+r.v)).toLowerCase().indexOf(f)>=0||r.d.toLowerCase().indexOf(f)>=0;
  const out=[];let last=null;
  for(const r of CVAR_ROWS){if(r.h||!hit(r))continue;if(r.grp&&r.grp!==last){out.push(r.grp);last=r.grp;}out.push(r);}
  return out;
}
function cvarRowClick(r){
  const why=cvarWhyNot(r.need);
  if(r.num||r.str){const i=cvEl&&cvEl.querySelector('input[data-cvar="'+r.n+'"]');if(i){i.focus();i.select();}return;}
  setCvar(r.n,CVARS[r.n]===r.v?CVAR_DEFAULTS[r.n]:r.v);
  if(why&&CVARS[r.n]===r.v){cvMsg=r.n+' '+r.v+' (no effect on this page: see below)';cvarMenuRender();}
}
function cvarMenuPlace(){
  if(!cvEl)return;
  const b=$('cvarBtn'),r=b.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-CV_GAP-CV_W;
  if(left<4)left=Math.min(r.right+CV_GAP,Math.max(4,vw-4-CV_W));
  if(left+CV_W>vw-4)left=Math.max(4,vw-4-CV_W);
  cvEl.style.left=left+'px';
  const avail=vh-8;cvEl.style.maxHeight=avail+'px';cvEl.style.top='4px';
  const h=Math.min(cvEl.getBoundingClientRect().height,avail);
  cvEl.style.top=Math.max(4,Math.min(r.top,vh-4-h))+'px';
}
function cvarMenuOpen(){
  cvarMenuClose();
  // a click anywhere else closes the list, including on its button (how it toggles)
  cvBack=document.createElement('div');
  cvBack.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  cvBack.onclick=ev=>{if(!cvEl||!cvEl.contains(ev.target))cvarMenuClose();};
  document.body.appendChild(cvBack);
  cvEl=document.createElement('div');cvEl.className='amPanel';cvEl.id='cvPanel';
  cvEl.innerHTML='<div class="amHead"><span class="amPathTxt">game cvars</span><span class="amCnt" id="cvHeadCnt"></span><button class="amReset" id="cvReset" title="Set every game cvar back to its default">Reset</button></div>'+
    '<input class="amSearch" id="cvSearch" type="text" spellcheck="false" autocomplete="off" placeholder="filter, or a cvar and value then Enter…">'+
    '<div class="amBody" id="cvBody"></div><div class="amNote" id="cvWhere"></div>';
  cvEl.querySelector('#cvReset').onclick=ev=>{ev.stopPropagation();resetCvars();};
  const se=cvEl.querySelector('#cvSearch');
  se.oninput=()=>{cvMsg='';cvarMenuRender();};
  // keep the focus in the filter box while rows are clicked (a row's mousedown would take
  // it); the value boxes take it as usual
  cvEl.addEventListener('mousedown',ev=>{if(ev.target.tagName==='INPUT')return;ev.preventDefault();});
  cvBack.appendChild(cvEl);
  document.addEventListener('keydown',cvarMenuKey,true);
  cvarMenuRender();cvarMenuPlace();se.focus();
}
function cvarMenuRender(){
  if(!cvEl)return;
  const bd=cvEl.querySelector('#cvBody'),sv=bd.scrollTop;bd.innerHTML='';
  const se=cvEl.querySelector('#cvSearch'),f=(se.value.trim().split(/\s+/)[0]||'');
  const rows=cvarRowsFor(CVAR_NAMES[f.toLowerCase()]||f);
  for(const r of rows){
    if(r.h){const d=document.createElement('div');d.className='amGrp';d.textContent=r.h;bd.appendChild(d);continue;}
    const why=cvarWhyNot(r.need),box=r.num||r.str,on=box?String(CVARS[r.n])!==String(CVAR_DEFAULTS[r.n]):CVARS[r.n]===r.v;
    const d=document.createElement('div');d.className='amItem'+(on?' on':'')+(why?' na':'');
    d.innerHTML='<span class="arw">'+(box?'#':(on?'✓':''))+'</span><span class="lbl">'+esc(r.n+(box?'':' '+r.v))+'</span>'+
      (r.num?'<input type="number" min="'+r.num[0]+'" max="'+r.num[1]+'" step="'+(r.step||1)+'" data-cvar="'+r.n+'" value="'+esc(CVARS[r.n])+'">':
       r.str?'<input type="text" class="wide" spellcheck="false" data-cvar="'+r.n+'" value="'+esc(CVARS[r.n])+'">':'')+
      '<span class="cnt">'+esc(r.d)+'</span>';
    d.title=r.t+(r.ng?'\n\n'+r.ng:'')+(why?'\n\n'+why:'')+(box?'':'\n\nClick to '+(on?'set it back to '+CVAR_DEFAULTS[r.n]:'set it')+'.');
    d.onclick=ev=>{if(ev.target.tagName==='INPUT')return;ev.stopPropagation();cvarRowClick(r);};
    if(box){const i=d.querySelector('input');i.onchange=()=>setCvar(r.n,i.value);}
    bd.appendChild(d);
  }
  if(!rows.length){const d=document.createElement('div');d.className='amNote';
    d.textContent=CVAR_NAMES[f.toLowerCase()]?'':'No cvar in this list matches that. Enter tries it as a command.';if(d.textContent)bd.appendChild(d);}
  const on=cvarsSet();
  cvEl.querySelector('#cvHeadCnt').textContent=on.length?on.length+' set':'all at default';
  cvEl.querySelector('#cvReset').disabled=!on.length;
  cvarWhereRender();
  bd.scrollTop=sv;
}
// g_nodecheck: the game builds the nodes again and stops the level with "Node check
// failed" once a node has 48 paths to check (PathNode::CheckPathTo, which prints the place
// of the node it was checking). The .pth keeps whether the build it was saved from failed;
// the nodes it gives 48 connections or more certainly did (the game counts every path it
// checks, the .pth only those it kept).
let NODECHECK=null;
function nodeCheckText(){
  if(NODECHECK!=null)return NODECHECK;
  const P=D.paths,C=D.f32(P.c),nc=C.length/9,cnt=new Int32Array(Math.max(1,P.n)),O=D.f32(P.o);
  for(let k=0;k<nc;k++){const i=C[k*9]|0;if(i>=0&&i<P.n)cnt[i]++;}
  const big=[];for(let i=0;i<P.n;i++)if(cnt[i]>=48)big.push(i);
  let h='<div>g_nodecheck: '+(P.fail?'<span class="warn">the build this .pth was saved from failed the node check (Node check failed)</span>':
    'the build this .pth was saved from passed the node check')+'</div>';
  if(big.length)h+='<div class="warn">'+big.length+' node'+(big.length>1?'s':'')+' with 48 connections or more: '+
    big.slice(0,8).map(i=>i+' ('+fnum(O[i*3])+' '+fnum(O[i*3+1])+' '+fnum(O[i*3+2])+')').join(', ')+(big.length>8?' …':'')+'</div>';
  else h+='<div>no node keeps 48 connections or more</div>';
  return NODECHECK=h;
}
// the list's foot: the last message, and what the cvars that are set found
function cvarWhereRender(){
  if(!cvEl)return;
  const el=cvEl.querySelector('#cvWhere');let h='';
  if(cvMsg)h+='<div class="msg">'+esc(cvMsg)+'</div>';
  if(GV){
    const l=gvPointLeaf(GV,cam.pos),c=GV.lf[l*14],a=GV.lf[l*14+1];
    h+='<div>camera: '+(c<0?'outside the map (in a leaf with no cluster: the game draws every leaf)':'cluster '+c+' of '+Math.max(GV.ncl,1)+', area '+a+(GV.na>1?' of '+GV.na:''))+'</div>';
    if(CVARS.r_lockpvs&&GV.marked)h+='<div>r_lockpvs: drawing what '+(GV.markCl<0?'a leaf outside the map (every leaf)':'cluster '+GV.markCl+', area '+GV.markArea)+' sees</div>';
    if(CVARS.r_novis)h+='<div>r_novis: every leaf is drawn</div>';
    // every direction: the game also drops what is outside the view, which isn't seen anyway
    if(CVARS.r_showtris&&GV.stats)h+='<div>drawn from here, all directions: '+GV.stats+'</div>';
    if(CVARS.r_shownormals&&GV.vn&&GV.nstats)h+='<div>r_shownormals, all directions: '+GV.nstats+'</div>';
    if(CVARS.r_showsky&&GV.skyTris!=null)h+='<div>r_showsky: '+GV.skyTris+' sky triangle'+(GV.skyTris===1?'':'s')+' in view, '+(GV.skyBlocks||0)+' blocks of the sky box</div>';
    if(!GV.pvs)h+='<div>this .bsp has no vis data: every cluster sees every other</div>';
  }else h+='<div>'+esc(cvarWhyNot('vis'))+'</div>';
  if(Math.trunc(CVARS.r_farplane)||CVARS.r_farplane_nofog){const ff=fogFar();
    h+='<div>farplane '+(ff>0?fnum(ff)+(Math.trunc(CVARS.r_farplane)?' (r_farplane)':' (the map\'s)'):'none')+(fogOn()?', fog '+fogCol().map(fnum).join(' '):', no fog')+'</div>';}
  if(CVARS.r_lightmap===2&&B.lmBright!=null)h+='<div>Brightest lightmap value: '+B.lmBright+'</div>';
  if(CVARS.r_light_showgrid&&LGRID)h+='<div>light grid: '+(LGRID.n||0)+' points within 256 units, '+LGRID.s.map(fnum).join(' x ')+' apart</div>';
  if(CVARS.cg_rain&&(WX.n||wxActive()))h+='<div>'+wxSummary()+'</div>';
  if(CVARS.sv_showentnums||CVARS.g_entinfo||CVARS.sv_showbboxes){gameEnts();const n=GAMEENTS.count;
    h+='<div>'+n+' entities spawn for g_gametype '+CVARS.g_gametype+', skill '+CVARS.skill+(CVARS.developer?', developer 1':'')+
      (n?': numbers '+CVARS.sv_maxclients+' to '+(CVARS.sv_maxclients+n-1):'')+', the world 1022</div>';}
  if(pathsOk()){
    const np=MAP.ents.reduce((s,e)=>s+(e.cls==='info_pathnode'&&!e.scr?1:0),0);
    h+='<div>AI paths: '+esc(D.paths.src||'')+', '+D.paths.n+' nodes'+(np!==D.paths.n?' <span class="warn">but the map has '+np+' info_pathnode: the file is from another version of the map (the game rebuilds it)</span>':'')+'</div>';
    if(CVARS.ai_shownode>0&&NODELIST)h+='<div>ai_shownode: '+(NODELIST.list.length?NODELIST.list.length+' node'+(NODELIST.list.length===1?'':'s')+' found from here':'no node in this cell at your height')+
      (NODELIST.lift>0.5?' (your feet lifted '+fnum(NODELIST.lift)+' units out of a brush)':'')+'</div>';
    if(CVARS.g_nodecheck)h+=nodeCheckText();
  }else if(routesOk()&&PA_GEN)h+='<div>AI paths: no .pth for this map, so the viewer worked them out as the game does when it loads it ('+PA_GEN.n+' nodes, '+PA_GEN.ms+' ms)</div>';
  else h+='<div>'+esc(cvarWhyNot('paths'))+'</div>';
  if(el._h!==h){el._h=h;el.innerHTML=h;cvarMenuPlace();}
}
function toggleCvarMenu(){if(cvEl)cvarMenuClose();else cvarMenuOpen();}

// ---- Modify's Spawnflags list: the game cvars list's look, without the filter box ----------
// Each row is one bit of the selected entity's spawnflags: its value, and its name in grey.
// A click ticks or unticks it. The names are the class's own (the entity definitions' QUAKED
// headers: D.defs[class].f, bit by bit), then the editor's (!Easy, !Medium...) that every class
// has; a path node has the Legend's (1 DONT_LINK, 2 DUCK ... 128 CRATE, 256 LOW_WALL_ARC).
let sfEl=null,sfBack=null;
window.addEventListener('resize',()=>{if(sfEl)sfMenuClose();});
function sfList(cls){
  if(cls==='info_pathnode')return [[1,'DONT_LINK']].concat(ACT_FLAGS,[[256,'LOW_WALL_ARC (Spearhead / Breakthrough only)',
    'LOW_WALL_ARC: Spearhead and Breakthrough only. The original game ignores it. The AI shoots from behind a wall within the "low_wall_arc" key\'s half-angle either side of the node\'s yaw (standing; crouching with DUCK). The "low_wall_arc" key sets this flag by itself']]);
  const d=(D.defs||{})[cls],names=d&&d.f?d.f:[],ed=D.editorFlags||{},out=[];
  for(let b=0;b<31;b++){
    const nm=b<names.length&&names[b]&&names[b].toLowerCase()!=='x'?names[b]:(ed[b]||'');
    if(nm)out.push([(1<<b)>>>0,nm]);}
  return out;
}
function sfMenuClose(){
  if(sfEl){sfEl.remove();sfEl=null;}
  if(sfBack){sfBack.remove();sfBack=null;}
  document.removeEventListener('keydown',sfMenuKey,true);}
function sfMenuKey(ev){
  // Esc closes it, and so does Alt+S again (the key that opened it)
  if(ev.key==='Escape'||(ev.altKey&&!ev.ctrlKey&&!ev.metaKey&&ev.key.toLowerCase()==='s')){sfMenuClose();ev.preventDefault();}
  ev.stopPropagation();}
function sfMenuPlace(){
  if(!sfEl)return;
  const r=$('bModSf').getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-CV_GAP-CV_W;
  if(left<4)left=Math.min(r.right+CV_GAP,Math.max(4,vw-4-CV_W));
  if(left+CV_W>vw-4)left=Math.max(4,vw-4-CV_W);
  sfEl.style.left=left+'px';
  const avail=vh-8;sfEl.style.maxHeight=avail+'px';sfEl.style.top='4px';
  const h=Math.min(sfEl.getBoundingClientRect().height,avail);
  sfEl.style.top=Math.max(4,Math.min(r.top,vh-4-h))+'px';
}
function sfMenuOpen(){
  sfMenuClose();
  if(!MOD.ents[MOD.sel])return;
  sfBack=document.createElement('div');
  sfBack.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  sfBack.onclick=ev=>{if(!sfEl||!sfEl.contains(ev.target))sfMenuClose();};
  document.body.appendChild(sfBack);
  sfEl=document.createElement('div');sfEl.className='amPanel';sfEl.id='sfPanel';
  sfEl.innerHTML='<div class="amHead"><span class="amPathTxt" id="sfTitle">spawnflags</span><span class="amCnt" id="sfCnt"></span><button class="amReset" id="sfClear" title="Take every spawnflag off">Clear</button></div>'+
    '<div class="amBody" id="sfBody"></div>';
  sfEl.querySelector('#sfClear').onclick=ev=>{ev.stopPropagation();sfSet(0);};
  sfEl.addEventListener('mousedown',ev=>ev.preventDefault());
  sfBack.appendChild(sfEl);
  document.addEventListener('keydown',sfMenuKey,true);
  sfRender();sfMenuPlace();
}
function toggleSfMenu(){if(sfEl)sfMenuClose();else sfMenuOpen();}
// the entity's spawnflags set to v (a change Undo takes back; 0 leaves the key out)
function sfSet(v){
  const m=MOD.ents[MOD.sel];if(!m)return;
  const cur=parseInt(modKv(m,'spawnflags')||'0',10)>>>0;v=v>>>0;if(v===cur)return;
  if(MOD.edit>=0)modEditClose(true);
  modHist();
  if(v)modSetKv(m,'spawnflags',String(v));
  else{const i=m.kv.findIndex(x=>x[0].toLowerCase()==='spawnflags');if(i>=0)m.kv.splice(i,1);}
  modChanged(modIsNode(m));
  flash(modName(m)+': spawnflags '+(v||'none'));
}
function sfRender(){
  if(!sfEl)return;
  const m=MOD.ents[MOD.sel];if(!m){sfMenuClose();return;}
  const cls=modCls(m),list=sfList(cls),cur=parseInt(modKv(m,'spawnflags')||'0',10)>>>0;
  sfEl.querySelector('#sfTitle').textContent='spawnflags: '+(cls||'entity');
  sfEl.querySelector('#sfCnt').textContent=cur?'= '+cur:'none set';
  sfEl.querySelector('#sfClear').disabled=!cur;
  const bd=sfEl.querySelector('#sfBody'),sv=bd.scrollTop;bd.innerHTML='';
  for(const[val,nm,tip]of list){
    const on=(cur&val)!==0,d=document.createElement('div');d.className='amItem'+(on?' on':'');
    d.innerHTML='<span class="arw">'+(on?'✓':'')+'</span><span class="lbl">spawnflags '+val+'</span><span class="cnt">'+esc(nm)+'</span>';
    d.title=(on?'On: click to take ':'Off: click to set ')+nm+' ('+val+')'+(tip?'\n\n'+tip:'');
    d.onclick=ev=>{ev.stopPropagation();sfSet(cur^val);};
    bd.appendChild(d);}
  if(!list.length){const d=document.createElement('div');d.className='amNote';
    d.textContent=(cls||'This entity')+' has no spawnflags defined.';bd.appendChild(d);}
  bd.scrollTop=sv;sfMenuPlace();
}

// ============================================================================
//  Picking: draw ids into a one-pixel target through a projection zoomed onto the pixel
// ============================================================================
function pickAt(x,y){
  if(!gl)return 0;
  gl.bindFramebuffer(gl.FRAMEBUFFER,B.pickFB);gl.viewport(0,0,1,1);
  const vp=viewProj([x,y]), px=new Uint8Array(4);
  const pass=mode=>{gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);drawScene(vp,mode);
    gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,px);return px[0]+px[1]*256+px[2]*65536;};
  let id=pass(1);
  // The game's sky was hit, so nothing else is under the pixel; every sky face is at the
  // far end there, so a second pass finds the nearest one (the brush you see).
  if(id&&id<=NF&&!simpleSky&&((TEX[SC.faceTex[id-1]]||{}).f&TF_SKY))id=pass(2)||id;
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,glcv.width,glcv.height);
  return id;
}
// What a pick id points at, plus the exact spot under the cursor.
function hitInfo(id,x,y){
  if(!id)return null;
  const h={id:id,face:-1,ent:-1,prim:-1,point:null};
  const ray=screenRay(x,y), e=cam.pos;
  if(id<=NF){
    const f=id-1;h.face=f;h.ent=SC.faceEnt[f];h.prim=SC.facePrim[f];
    // the exact point: the face's plane for brushes, its triangles otherwise
    const pl=SC.facePlane[f];
    if(pl&&SC.faceKind[f]===0){const dn=vdot(pl,ray);if(Math.abs(dn)>1e-6){const t=(pl[3]-vdot(pl,e))/dn;if(t>0)h.point=[e[0]+ray[0]*t,e[1]+ray[1]*t,e[2]+ray[2]*t];}}
    if(!h.point)h.point=rayTris(e,ray,SC.faceI0[f],SC.faceIN[f]);
  }else{
    h.ent=id-NF-1;const X=ENTS[h.ent];h.point=X&&X.origin?X.origin.slice():null;
  }
  return h;
}
function rayTris(o,d,i0,n){
  let best=Infinity;const P=SC.pos,T=SC.tri;
  for(let k=i0;k<i0+n;k+=3){
    const a=T[k]*3,b=T[k+1]*3,c=T[k+2]*3;
    const e1=[P[b]-P[a],P[b+1]-P[a+1],P[b+2]-P[a+2]],e2=[P[c]-P[a],P[c+1]-P[a+1],P[c+2]-P[a+2]];
    const pv=vcross(d,e2),det=vdot(e1,pv);if(Math.abs(det)<1e-9)continue;
    const tv=[o[0]-P[a],o[1]-P[a+1],o[2]-P[a+2]],u=vdot(tv,pv)/det;if(u<0||u>1)continue;
    const qv=vcross(tv,e1),v=vdot(d,qv)/det;if(v<0||u+v>1)continue;
    const t=vdot(e2,qv)/det;if(t>0&&t<best)best=t;}
  return isFinite(best)?[o[0]+d[0]*best,o[1]+d[1]*best,o[2]+d[2]*best]:null;
}

// ============================================================================
//  Selection
// ============================================================================
function isWorldlike(ei){return !!WORLDLIKE[MAP.ents[ei].cls];}
function keyOfHit(h){return(h.ent>0&&!isWorldlike(h.ent))?'e'+h.ent:(h.prim>=0?'p'+h.prim:(h.ent>=0?'e'+h.ent:null));}
function selectedEnts(){const s=new Set();for(const k of SEL)if(k[0]==='e')s.add(+k.slice(1));return s;}
function selectedPrims(){const s=[];for(const k of SEL)if(k[0]==='p')s.push(+k.slice(1));return s;}
let ENTPRIMS=null;
function primsOfEnt(ei){
  if(!ENTPRIMS){ENTPRIMS=MAP.ents.map(()=>[]);SC.prims.forEach((p,pi)=>ENTPRIMS[p.ent].push(pi));}
  return ENTPRIMS[ei];
}
function rebuildSelection(){
  if(!gl)return;
  const tri=[],edg=[];
  const addPrim=pi=>{const p=SC.prims[pi];for(let f=p.f0;f<p.f1;f++){if(faceVis&&!faceVis[f])continue;
    const a=SC.faceI0[f],c=SC.faceIN[f];for(let k=a;k<a+c;k++)tri.push(SC.tri[k]);
    const ea=SC.faceE0[f],ec=SC.faceEN[f];for(let k=ea;k<ea+ec;k++)edg.push(SC.edge[k]);}};
  const selE=selectedEnts();
  for(const pi of selectedPrims())addPrim(pi);
  for(const ei of selE)for(const pi of primsOfEnt(ei))addPrim(pi);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.sel);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(tri.length?tri:[0,0,0]),gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.selE);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(edg.length?edg:[0,0]),gl.DYNAMIC_DRAW);
  selTriCount=tri.length;selEdgeCount=edg.length;
  const mi=[];for(const ei of selE){const X=ENTS[ei];if(X.mvn&&entShown(ei))for(let k=0;k<X.mvn;k++)mi.push(X.mv0+k);}
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.mSel);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(mi.length?mi:[0,0,0]),gl.DYNAMIC_DRAW);
  markSelCount=mi.length;
  for(const R of MODELS){const a=[];for(const ei of R.inst)if(selE.has(ei)&&entShown(ei))a.push(...instData(ei));
    gl.bindBuffer(gl.ARRAY_BUFFER,R.selBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a.length?a:new Array(INST_FLOATS).fill(0)),gl.DYNAMIC_DRAW);R.nsel=a.length/INST_FLOATS;}
  lineDirty=true;
}
// What the mouse is over gets an outline in the accent colour: the edges of a brush (or of
// all of a brush entity's brushes), and for a model or marker, which has no edges of its
// own, its box as the selection shows it, a little larger so it never hides in a face.
// The selection itself isn't outlined again.
function setHover(h){
  const key=h?keyOfHit(h):null;
  setHover.h=h;
  if(key===setHover.key)return;setHover.key=key;
  const edg=[], L=[];
  if(key&&!SEL.has(key)){
    const prims=key[0]==='p'?[+key.slice(1)]:primsOfEnt(+key.slice(1));
    for(const pi of prims){const p=SC.prims[pi];for(let f=p.f0;f<p.f1;f++){if(faceVis&&!faceVis[f])continue;const ea=SC.faceE0[f],ec=SC.faceEN[f];for(let k=ea;k<ea+ec;k++)edg.push(SC.edge[k]);}}
    const X=key[0]==='e'?ENTS[+key.slice(1)]:null;
    if(X&&X.box&&!edg.length){
      const b=X.box,g=X.marker?2:0.5;
      const P=boxCorners({mins:b.mins.map(v=>v-g),maxs:b.maxs.map(v=>v+g),ax:b.ax},b.origin),C=k=>P[k];
      for(const[a,c]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]])L.push(...C(a),...C(c));
    }
  }
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,B.hovE);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(edg.length?edg:[0,0]),gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.hovBox);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(L.length?L:[0,0,0]),gl.DYNAMIC_DRAW);
  hovEdgeCount=edg.length;hovBoxVerts=L.length/3;requestDraw();
}
setHover.key=null;setHover.h=null;
// a click that selects what is under the mouse takes its hover outline away
function refreshHover(){if(!gl)return;setHover.key=undefined;setHover(setHover.h);}
function selectionChanged(){modSyncSel();rebuildSelection();refreshHover();updateSelPanel();if($('info').classList.contains('on'))showInfo(infoMode==='errs'||infoMode==='leak'||infoMode==='scr'?'sel':infoMode);requestDraw();listSoon();}
// The Find lists show what is selected in green, however it was selected (a click in the
// view, Enter in the search box, a list row): they are drawn again once, a frame after.
let _listRaf=0;
function listSoon(){if(_listRaf)return;_listRaf=requestAnimationFrame(()=>{_listRaf=0;if(MAP&&SC)renderList();});}
function clickSelect(h,mods){
  if(mods.ctrl&&mods.shift&&!mods.alt){faceInfoAt(h);return;}
  if(mods.ctrl&&mods.alt){selectPath(h,mods.shift);return;}
  if(!h){if(!mods.shift){SEL.clear();lastHit=null;selectionChanged();}return;}
  const key=keyOfHit(h);if(!key)return;
  lastHit=h;
  if(mods.alt){selectSameKind(h,mods.shift);return;}
  if(mods.shift){if(SEL.has(key))SEL.delete(key);else SEL.add(key);}
  else{SEL.clear();SEL.add(key);}
  selectionChanged();
  if(mods.ctrl)showInfo('sel');
}
// Alt+click: every entity of the same class, or every brush using the same texture.
function selectSameKind(h,add){
  if(!add)SEL.clear();
  if(h.ent>0&&!isWorldlike(h.ent)){
    const cls=MAP.ents[h.ent].cls;let n=0;
    for(let ei=1;ei<MAP.ents.length;ei++)if(MAP.ents[ei].cls===cls&&!hidEnt.has(ei)){SEL.add('e'+ei);n++;}
    flash(n+' x '+cls+' selected');
  }else if(h.face>=0){selectByTexture(SC.faceTex[h.face],true);}
  selectionChanged();
}
// Same spawnflags: every shown entity of the same class whose spawnflags are the same (for
// example every CRATE path node). Needs a selected entity with non-zero spawnflags.
function sfOf(ei){return ei>0&&!isWorldlike(ei)?(parseInt(MAP.ents[ei].kvl.spawnflags||'0',10)|0):0;}
function selectSameSpawnflags(ei){
  const sf=sfOf(ei);
  if(!sf){flash('Select an entity that has spawnflags');return;}
  const cls=MAP.ents[ei].cls;let n=0;SEL.clear();
  for(let i=1;i<MAP.ents.length;i++)if(MAP.ents[i].cls===cls&&sfOf(i)===sf&&entShown(i)){SEL.add('e'+i);n++;}
  selectionChanged();
  flash(n+' x '+cls+' with spawnflags '+sf+' selected');
}
// Same error: the errors the viewer shows on path nodes (the ones with a warning tag when AI
// errors are on, and Modify's problems): no paths, one-way, a duplicate node, no angle, in the
// wall, 48 paths full, and Modify's own (own group, cell full). Worked out for a map's path
// nodes from the paths in use (PA), whether or not ai_showroutes is on. An "own group" note is
// information only and doesn't count.
let PNERR_C=null,PNIDX=null;
function pnErrCtx(A){
  const fh=CVARS.ai_fallheight;
  if(PNERR_C&&PNERR_C.A===A&&PNERR_C.fh===fh)return PNERR_C;
  const n=A.n,C=A.c,nc=C.length/9,first=new Int32Array(n+1),ow=new Int32Array(n);
  for(let k=0;k<nc;k++){const i=C[k*9]|0;if(i>=0&&i<n)first[i+1]++;}
  for(let i=0;i<n;i++)first[i+1]+=first[i];
  for(let i=0;i<n;i++)for(let k=first[i];k<first[i+1];k++){
    const to=C[k*9+1]|0,fall=C[k*9+2];if(fall>fh||to<0||to>=n)continue;
    let rev=false;for(let j=first[to+1]-1;j>=first[to];j--)if(C[j*9+2]<fh&&(C[j*9+1]|0)===i){rev=true;break;}
    if(!rev)ow[i]++;}
  return PNERR_C={A:A,fh:fh,first:first,ow:ow};
}
// node i's errors: id -> what to call it
function pnErrKinds(A,i){
  const X=pnErrCtx(A),kinds=new Map(),F=A.f[i];
  if(pnGone(A,i))return kinds;
  if(X.first[i]===X.first[i+1]){
    if(F&1){if(!(nodeSpawnflags(A,i)&1))kinds.set('dup','a duplicate of an earlier node: not linked');}
    else kinds.set('none','no paths');}
  if(X.ow[i]>0)kinds.set('ow','one-way paths');
  if(nodeNoAngle(A,i))kinds.set('noangle','no angle');
  if(!(F&1)&&nodeWall([A.o[i*3],A.o[i*3+1],A.o[i*3+2]]))kinds.set('wall','in the wall');
  if(paOver().over.has(i))kinds.set('links','48 paths: full');
  const R=paIssues();
  if(R)for(const x of R.node.get(i)||[])if(x.lv!==0&&!kinds.has(x.k))kinds.set(x.k,x.lbl||({links:'48 paths: full',none:'no paths',cell:'cell full',wall:'in the wall',island:'own group'})[x.k]||x.k);
  return kinds;
}
// the map's path node entity -> its node number in the paths (the .pth keeps the map's order)
function pnIndexMap(A){
  const pn=pnEnts(),n0=A.n0==null?A.n:A.n0;
  if(pn.length!==n0)return null;
  if(!PNIDX||PNIDX.pn!==pn){PNIDX={pn:pn,m:new Map()};pn.forEach((ei,k)=>PNIDX.m.set(ei,k));}
  return PNIDX.m;
}
// the errors of the selected path nodes together, or null when none is selected
function selNodeErrors(){
  const sel=[...selectedEnts()].filter(ei=>MAP.ents[ei]&&MAP.ents[ei].cls==='info_pathnode');
  if(!sel.length||!routesOk())return null;
  const A=PA();if(!A)return null;
  const im=pnIndexMap(A);if(!im)return null;
  const kinds=new Map();
  for(const ei of sel){const k=im.get(ei);if(k==null||k>=A.n)continue;for(const[id,t]of pnErrKinds(A,k))kinds.set(id,t);}
  return{A:A,im:im,kinds:kinds};
}
function selectSameError(){
  const e=selNodeErrors();
  if(!e||!e.kinds.size){flash('Select a path node that has an error first');return;}
  const want=[...e.kinds.keys()];let n=0;
  const hit=new Set();
  for(const[ei,k]of e.im){if(!entShown(ei)||k>=e.A.n)continue;
    const ks=pnErrKinds(e.A,k);if(want.some(id=>ks.has(id)))hit.add(ei);}
  SEL.clear();for(const ei of hit){SEL.add('e'+ei);n++;}
  selectionChanged();
  flash(n+' path node'+(n===1?'':'s')+' with: '+[...e.kinds.values()].join(', '));
}
// Ctrl+Shift+click (or middle-click): the texture card of the clicked face (in Radiant,
// Ctrl+Shift+click selects a single face). Models and markers have no face of their own.
function faceInfoAt(h){
  if(h&&h.face>=0){lastHit=h;showInfo('face');}
  else flash(h?'No face there: Ctrl+Shift+click a brush, patch or terrain face for its texture':'Nothing there');
}
// Ctrl+Alt+click: the whole path through an entity, following its "target" -> "targetname"
// links both ways: everything it leads to, again and again, and everything that leads to
// it (path nodes, spline paths, a trigger and what it fires...). Shift adds to the selection.
let TARGETED_BY=null;                     // targetname -> the entities whose "target" names it
function pathOf(ei){
  if(!TARGETED_BY){TARGETED_BY=new Map();
    MAP.ents.forEach((e,i)=>{const t=e.kvl.target;if(t){let l=TARGETED_BY.get(t);if(!l)TARGETED_BY.set(t,l=[]);l.push(i);}});}
  let loop=false;
  const walk=next=>{const seen=new Set([ei]),q=[ei];
    while(q.length){const i=q.pop();for(const j of next(i)){if(j===ei)loop=true;if(!seen.has(j)){seen.add(j);q.push(j);}}}
    seen.delete(ei);return seen;};
  const after=walk(i=>{const t=MAP.ents[i].kvl.target;return t?(ENTS.tn.get(t)||[]):[];});
  const before=walk(i=>{const n=MAP.ents[i].kvl.targetname;return n?(TARGETED_BY.get(n)||[]):[];});
  for(const i of after)before.delete(i);
  return{after:after,before:before,loop:loop};
}
function selectPath(h,add){
  const ei=h?h.ent:-1;
  if(!(ei>0)||isWorldlike(ei)){flash('Ctrl+Alt+click an entity with a "target" (a path node, spline path, trigger...)');return;}
  const p=pathOf(ei);
  if(!add)SEL.clear();
  let n=0;
  for(const i of [ei,...p.before,...p.after])if(entShown(i)){SEL.add('e'+i);n++;}
  lastHit=h;selectionChanged();
  if(!p.before.size&&!p.after.size){flash(entName(ei)+' has no "target" and nothing targets it');return;}
  const hid=1+p.before.size+p.after.size-n;
  flash('Path through '+entName(ei)+': '+n+' selected, '+p.before.size+' before it and '+p.after.size+' after it'+
    (p.loop?' (it loops)':'')+(hid?', '+hid+' hidden':''));
}
// The entity Same path and Same targetname act on: the one selected, else the one last
// clicked (when it is still selected).
function selFocusEnt(){
  const ents=[...selectedEnts()];
  return ents.length===1?ents[0]:(lastHit&&lastHit.ent>0&&SEL.has('e'+lastHit.ent))?lastHit.ent:-1;
}
// Same targetname ($): every entity with that entity's targetname, the group a script
// reaches as $name.
function selectSameTargetname(ei){
  const tn=(ei>0&&!isWorldlike(ei))?MAP.ents[ei].kvl.targetname:'';
  if(!tn){flash('Select an entity that has a targetname: $ then selects every entity with the same one');return;}
  const l=ENTS.tn.get(tn)||[];
  SEL.clear();let n=0;for(const i of l)if(entShown(i)){SEL.add('e'+i);n++;}
  if(!SEL.size)SEL.add('e'+ei);
  selectionChanged();
  flash(l.length<2?'No other entity is named $'+tn:n+' x $'+tn+' selected'+(l.length>n?', '+(l.length-n)+' hidden':''));
}
// Everything shown that uses a texture (texUse): each world brush with a face in it, each brush
// entity, and each entity whose model draws it (a static prop's or a script_model's).
function selectByTexture(ti,add){
  if(!add)SEL.clear();let nb=0,ne=0;
  for(const[k,o]of texUse(ti).keys){if(!useShown(o))continue;SEL.add(k);if(k[0]==='e')ne++;else nb++;}
  const nm=TEX[ti]?TEX[ti].n.replace(/^textures\//,''):'?';
  flash(nb||ne?nm+': '+[nb?nb+' brush'+(nb===1?'':'es'):'',ne?ne+' entit'+(ne===1?'y':'ies'):''].filter(Boolean).join(' and ')+' selected'
    :nm+': nothing that is shown uses it');
}
function selectClass(cls,add){if(!add)SEL.clear();for(let ei=1;ei<MAP.ents.length;ei++)if(MAP.ents[ei].cls===cls)SEL.add('e'+ei);selectionChanged();}
function selBounds(){
  const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  const grow=(a,b)=>{for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],a[k]);mx[k]=Math.max(mx[k],b[k]);}};
  for(const pi of selectedPrims()){const p=SC.prims[pi];if(isFinite(p.mins[0]))grow(p.mins,p.maxs);}
  for(const ei of selectedEnts()){const X=ENTS[ei],b=X.box,dx=X.hasGeo?doorXf(ei):null;
    if(dx){const q=ptsBounds(doorCorners(movObj(ei),dx));grow(q.mins,q.maxs);}
    else if(b){const o=b.origin;grow([o[0]+b.wmins[0],o[1]+b.wmins[1],o[2]+b.wmins[2]],[o[0]+b.wmaxs[0],o[1]+b.wmaxs[1],o[2]+b.wmaxs[2]]);}
    else if(X.anchor)grow(X.anchor,X.anchor);}
  return isFinite(mn[0])?{mins:mn,maxs:mx}:null;
}
// Every Hide and Show all goes on a stack that Ctrl+Z (or the Undo button) unwinds one step
// at a time: a Hide shows those things again, a Show all hides again what it showed.
const HIDE_UNDO=[];
function hideSelection(){
  if(!SEL.size)return;
  const step={e:[],p:[]};
  for(const k of SEL){const n=+k.slice(1);
    if(k[0]==='e'){if(!hidEnt.has(n)){hidEnt.add(n);step.e.push(n);}}else if(!hidPrim.has(n)){hidPrim.add(n);step.p.push(n);}}
  if(step.e.length||step.p.length){HIDE_UNDO.push(step);if(HIDE_UNDO.length>500)HIDE_UNDO.shift();}
  const n=SEL.size;SEL.clear();rebuildWorld();updateSelPanel();flash(n+' hidden - Ctrl+Z undoes, Shift+H shows everything');
}
function unhideAll(){
  if(hidEnt.size||hidPrim.size)HIDE_UNDO.push({all:true,e:[...hidEnt],p:[...hidPrim]});
  hidEnt.clear();hidPrim.clear();rebuildWorld();updateSelPanel();}
function undoHide(){
  const step=HIDE_UNDO.pop();
  if(!step){flash('Nothing to undo: Ctrl+Z undoes a Hide or Show all');return;}
  if(step.mod){const m=step.mod;
    if(MOD.ents.includes(m)){m.hid=step.was;modChanged(false);flash('Undo: '+modName(m)+(m.hid?' hidden':' shown')+' again'+(HIDE_UNDO.length?' (Ctrl+Z again for the step before)':''));}
    else undoHide();                          // removed since: the step before
    return;}
  const n=step.e.length+step.p.length;
  // a Show all, or a Shift+click on a list square that showed hidden entities again
  if(step.all||step.show){for(const i of step.e)hidEnt.add(i);for(const i of step.p)hidPrim.add(i);}
  else{for(const i of step.e)hidEnt.delete(i);for(const i of step.p)hidPrim.delete(i);}
  rebuildWorld();updateSelPanel();
  flash((step.all?'Undo Show all: '+n+' hidden again':step.show?'Undo Show: '+n+' hidden again':'Undo Hide: '+n+' shown again')+(HIDE_UNDO.length?' (Ctrl+Z again for the step before)':''));
}

// ============================================================================
//  Camera movement
// ============================================================================
const keys=new Set();
let radFly=null;          // Radiant right-button flight: {x,y} cursor
let flyAnim=null;
function moveBy(v,s){cam.pos[0]+=v[0]*s;cam.pos[1]+=v[1]*s;cam.pos[2]+=v[2]*s;}
let _lastT=performance.now();
function loop(t){
  requestAnimationFrame(loop);
  const dt=Math.min(0.1,(t-_lastT)/1000);_lastT=t;
  if(!SC)return;
  if((keys.size||radFly)&&!document.hasFocus())stopCamera();
  let moved=false;
  if(flyAnim){const k=Math.min(1,(t-flyAnim.t0)/flyAnim.dur),s=k*k*(3-2*k);
    for(let i=0;i<3;i++)cam.pos[i]=flyAnim.from[i]+(flyAnim.to[i]-flyAnim.from[i])*s;
    if(flyAnim.yaw!=null){cam.yaw=flyAnim.y0+(flyAnim.yaw-flyAnim.y0)*s;cam.pitch=flyAnim.p0+(flyAnim.pitch-flyAnim.p0)*s;}
    if(flyAnim.roll!=null)cam.roll=flyAnim.r0+(flyAnim.roll-flyAnim.r0)*s;
    if(k>=1)flyAnim=null;moved=true;}
  const k=c=>keys.has(c), fast=k('Shift')?4:1, a=camAxes(), sp=moveSpeed*fast*dt;
  if(keys.size&&!typing()){
    if(camMode==='free'){
      // W / S along the view line; with Ctrl held, level with the ground as Up / Down
      const WS=k('w')?1:k('s')?-1:0, ctl=k('Control');
      const F=ctl?0:WS, R=k('d')?1:k('a')?-1:0, U=(k(' ')?1:0)-(k('c')?1:0);
      // Up / Down (and Ctrl+W / Ctrl+S): forward and back level with the ground (the way the
      // camera faces, its pitch taken out), whichever way it looks up or down
      const FH=k('arrowup')?1:k('arrowdown')?-1:ctl?WS:0;
      if(FH){const y=cam.yaw*Math.PI/180;moveBy([Math.cos(y),Math.sin(y),0],sp*FH);moved=true;}
      // A / D strafe along the screen's right (the tilted one, a.r) and Space / C rise along
      // the screen's up: world up turned about the view line by the tilt, so with no tilt
      // they go straight up and down, as in the Model Viewer's free-look.
      if(F){moveBy(a.f,sp*F);moved=true;} if(R){moveBy(a.r,sp*R);moved=true;}
      if(U){const P=cam.pitch*Math.PI/180,c=Math.cos(P),s=Math.sin(P);
        moveBy([c*a.u[0]-s*a.f[0],c*a.u[1]-s*a.f[1],c*a.u[2]-s*a.f[2]],sp*U);moved=true;}
      if(k('arrowleft')){lookBy(-90*dt*fast,0);moved=true;} if(k('arrowright')){lookBy(90*dt*fast,0);moved=true;}
      // Q tilts the head to the left shoulder, E to the right, as in the Model Viewer: a
      // positive roll turns camAxes' right axis up (the horizon's right end drops on screen).
      if(k('q')){cam.roll+=60*dt;moved=true;} if(k('e')){cam.roll-=60*dt;moved=true;}
    }else if(!k('Control')){
      const F=k('arrowup')?1:k('arrowdown')?-1:0, R=k('.')?1:k(',')?-1:0, U=k('d')?1:k('c')?-1:0;
      if(F){moveBy(a.f,sp*F);moved=true;} if(R){moveBy(a.r,sp*R);moved=true;} if(U){moveBy([0,0,1],sp*U);moved=true;}
      if(k('arrowleft')){lookBy(-90*dt*fast,0);moved=true;} if(k('arrowright')){lookBy(90*dt*fast,0);moved=true;}
      if(k('a')){lookBy(0,-60*dt*fast);moved=true;} if(k('z')){lookBy(0,60*dt*fast);moved=true;}
    }
  }
  if(radFly){
    // MOHRadiant's right-button flight (Cam_MouseControl in the Radiant camera window):
    // the cursor's distance from the middle of the view sets the speed, up/down to fly
    // forward/back and left/right to turn, with a small dead zone in the middle.
    let xf=(radFly.x-W/2)/(W/2), yf=(H/2-radFly.y)/(H/2);
    xf*=1-Math.abs(yf);
    if(xf<0){xf+=0.1;if(xf>0)xf=0;}else{xf-=0.1;if(xf<0)xf=0;}
    if(Math.abs(yf)<0.05)yf=0;
    if(yf){moveBy(a.f,yf*moveSpeed*fast*dt*1.5);moved=true;}
    if(xf){lookBy(xf*dt*150,0);moved=true;}
  }
  // doors on the move, or waiting to close
  const doors=DOORS_BUSY.size?doorsAdvance(performance.now()):false;
  // exploders going off
  const exps=EXP.busy.size?expAdvance(performance.now()):false;
  // moving leaves (deformVertexes on models): redrawn 30 times a second while any is seen
  const sway=dvActive()&&performance.now()-DVT.at>=33;if(sway)DVT.at=performance.now();
  // thunder's flashes
  thTick(performance.now());
  // the weather: its client frames run with the page's clock while drops fall or can start
  let wx=false;
  if(wxActive()){wxAdvance(performance.now());wx=true;}else WX.wall=0;
  // Simulate's model in flight (a camera moved by hand stops following it)
  if(moved&&SIM.run&&$('simCam').checked){$('simCam').checked=false;flash('The camera no longer follows the model');}
  if(moved&&ACT.follow){ACT.follow=false;simPanel();flash('Follow off: the camera was moved by hand');}
  const sims=(SIM.run?simTick(performance.now()):false)||actTick(performance.now());
  if(moved)camChanged();
  if(moved||doors||exps||wx||sway||sims||_drawReq){_drawReq=false;draw();}
}
// Turn the view dx degrees right and dy degrees down as seen on the screen. With the camera
// tilted (Q / E), the screen's right and down are tilted too, so the turn is rotated by the
// roll before it becomes yaw and pitch, as in the Model Viewer's free-look: dragging down
// on a tilted screen still looks toward the bottom of the screen.
function lookBy(dx,dy){
  const R=cam.roll*Math.PI/180, c=Math.cos(R), s=Math.sin(R);
  cam.yaw-=c*dx+s*dy; cam.pitch+=c*dy-s*dx;
}
function camChanged(){
  cam.pitch=Math.max(-89,Math.min(89,cam.pitch));
  cam.yaw=((cam.yaw%360)+360)%360;
  hoverDirty=true;
}
function lookFrom(target,dist){
  const a=camAxes();
  return[target[0]-a.f[0]*dist,target[1]-a.f[1]*dist,target[2]-a.f[2]*dist];
}
// ---- Eye view: what the entity sees, as the game would put an eye there --------------
// Player starts: the player is spawned with its feet at the start (set on the floor); its
// eye is DEFAULT_VIEWHEIGHT (82, bg_public.h) above them. Path nodes, waypoints and the
// actors' own spots: the AI stands on the floor under them, so the same height above it.
// Cameras, spline paths and everything else: from its origin exactly. It looks the way the
// entity's angles say, or else at what its "target" names.
const EYE_GROUND=/^(info_player_(start|deathmatch|allied|axis)|info_pathnode|info_waypoint|info_vehiclepoint|ai_|actor$)/;
function eyeView(ei){
  const e=MAP.ents[ei],X=ENTS[ei];if(!e||!X)return null;
  const o=X.origin||parseVec(e.kvl.origin,3);if(!o)return null;
  const kv=Object.assign({},e.kvl);const tg=gameKey(ei,'target');if(tg)kv.target=tg;
  return eyeViewFrom(e.cls,kv,o,entName(ei),ei,false);
}
// Eye view of an entity given by its class, keys and origin (a map entity's, or one added in
// Modify: any = true faces yaw 0 when it has neither angles nor a target, else there is none)
function eyeViewFrom(cls,kvl,o,name,ei,any){
  const hasAng=kvl.angle!=null||kvl.angles!=null;
  let tgt=null;const tg=kvl.target;
  if(tg){const t=(typeof gameTn==='function'?gameTn(tg):ENTS.tn.get(tg))||[];for(const ti of t){const Y=ENTS[ti];if(Y&&(Y.anchor||Y.origin)&&ti!==ei){tgt=Y.anchor||Y.origin;break;}}}
  // a player start with no angle still faces somewhere: yaw 0, as the game spawns it
  const spawn=/^info_player_(start|deathmatch|allied|axis)$/.test(cls);
  if(!hasAng&&!tgt&&!spawn&&!any)return null;
  const ground=EYE_GROUND.test(cls);
  let pos=o.slice();
  // (a player start is already at the feet: mappers set it on the floor, and dropping it
  // could fall through a vehicle the player starts on)
  if(ground){if(!spawn)try{const d=pgDrop(o);if(isFinite(d[2])&&o[2]-d[2]<2048)pos=[o[0],o[1],d[2]];}catch(_e){}pos[2]+=82;}
  let ang;
  if(hasAng||!tgt){const a=hasAng?entAngles(kvl):[0,0,0];ang=[a[0]||0,a[1]||0,a[2]||0];}
  else{const v=[tgt[0]-pos[0],tgt[1]-pos[1],tgt[2]-pos[2]],h=Math.hypot(v[0],v[1]);
    ang=[-Math.atan2(v[2],h)*180/Math.PI,Math.atan2(v[1],v[0])*180/Math.PI,0];}
  const how=hasAng?'its angles ( '+ang.map(fnum).join(' ')+' )':tgt?'its target $'+tg:'yaw 0 (it has no angle)';
  return{pos:pos,ang:ang,
    why:'Eye view: put the camera '+(ground?'82 units (the player\'s eye height, DEFAULT_VIEWHEIGHT) above '+(spawn?'it':'the floor under it')+', as '+(/^info_player/.test(cls)?'a player spawned here sees':'someone standing here sees'):'at its origin, as it sees in game')+', looking the way '+how+' says',
    flash:'Eye view from '+name+(ground?(spawn?' (82 units above it)':' (82 units above the floor)'):' (its origin)')+', facing '+how};
}
function flyTo(pos,yaw,pitch,roll){flyAnim={t0:performance.now(),dur:450,from:cam.pos.slice(),to:pos,y0:cam.yaw,p0:cam.pitch,r0:cam.roll,yaw:yaw,pitch:pitch,roll:null};
  if(yaw!=null){let d=yaw-cam.yaw;while(d>180)d-=360;while(d<-180)d+=360;flyAnim.yaw=cam.yaw+d;}
  if(roll!=null){let d=roll-cam.roll;while(d>180)d-=360;while(d<-180)d+=360;flyAnim.roll=cam.roll+d;}}
// The camera's angles as the game writes them, ( pitch yaw roll ): pitch and yaw as camAxes
// takes them (AngleVectors: looking down is a positive pitch), the roll the other way round,
// since camAxes turns the right axis up for a positive roll and AngleVectors turns it down.
// Pitch and roll in -180..180, yaw in 0..360.
function wrap180(a){a=((a%360)+360)%360;return a>180?a-360:a;}
function camAngles(){return[wrap180(cam.pitch),((cam.yaw%360)+360)%360,wrap180(-cam.roll)];}
// Turn the camera to angles the game way round (as camAngles gives them), where it is.
function turnTo(p,y,r){flyTo(cam.pos.slice(),y,Math.max(-89,Math.min(89,wrap180(p))),-r);}
// the numbers of a vector typed or pasted, its brackets and commas aside
function vecNums(s){return(String(s).match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi)||[]).map(Number);}
function focusSelection(){
  const b=selBounds();if(!b){flash('Nothing selected');return;}
  const c=[(b.mins[0]+b.maxs[0])/2,(b.mins[1]+b.maxs[1])/2,(b.mins[2]+b.maxs[2])/2];
  const r=Math.max(16,Math.hypot(b.maxs[0]-b.mins[0],b.maxs[1]-b.mins[1],b.maxs[2]-b.mins[2])/2);
  const dist=Math.min(6000,r/Math.tan(Math.min(fovX,70)*Math.PI/360)*1.15+24);
  // keep the current heading, look at the selection's middle
  const a=camAxes();let dir=vnorm(vsub(c,cam.pos))||a.f;
  const yaw=Math.atan2(dir[1],dir[0])*180/Math.PI, pitch=-Math.asin(Math.max(-1,Math.min(1,dir[2])))*180/Math.PI;
  const D2=Math.PI/180, f=[Math.cos(pitch*D2)*Math.cos(yaw*D2),Math.cos(pitch*D2)*Math.sin(yaw*D2),-Math.sin(pitch*D2)];
  flyTo([c[0]-f[0]*dist,c[1]-f[1]*dist,c[2]-f[2]*dist],yaw,pitch);
}
function startView(){
  for(const cls of ['info_player_start','info_player_deathmatch','info_player_allied','info_player_axis']){
    const ei=MAP.ents.findIndex(e=>e.cls===cls);
    if(ei>=0){const o=parseVec(MAP.ents[ei].kvl.origin,3);if(o){const a=entAngles(MAP.ents[ei].kvl);return{p:[o[0],o[1],o[2]+82],y:a[1],pi:0};}}}
  const w=worldBounds();
  const c=[(w.mins[0]+w.maxs[0])/2,(w.mins[1]+w.maxs[1])/2,(w.mins[2]+w.maxs[2])/2];
  const r=Math.hypot(w.maxs[0]-w.mins[0],w.maxs[1]-w.mins[1])/2||512;
  return{p:[c[0]-r*0.9,c[1]-r*0.9,c[2]+r*0.6],y:45,pi:28};
}
function worldBounds(){const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  for(const p of SC.prims){if(!isFinite(p.mins[0]))continue;for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],p.mins[k]);mx[k]=Math.max(mx[k],p.maxs[k]);}}
  return isFinite(mn[0])?{mins:mn,maxs:mx}:{mins:[-512,-512,-512],maxs:[512,512,512]};}
function resetCam(){const s=startView();flyTo(s.p,s.y,s.pi);cam.roll=0;}
// PgUp / PgDn: hop to the next floor above or below, as MOHRadiant's UpFloor / DownFloor do.
function changeFloor(up){
  const x=cam.pos[0],y=cam.pos[1],feet=cam.pos[2]-82;let best=null;
  for(let f=0;f<SC.nf;f++){
    if(SC.faceKind[f]!==0||!faceVis[f])continue;const pl=SC.facePlane[f];if(!pl||pl[2]<0.7)continue;
    const z=(pl[3]-pl[0]*x-pl[1]*y)/pl[2];
    if(up?(z<=feet+16):(z>=feet-16))continue;
    if(best!=null&&(up?z>=best:z<=best))continue;
    // inside the face's outline seen from above?
    const v0=SC.faceV0[f],n=SC.faceVN[f],P=SC.pos;let inside=true;
    for(let q=0;q<n;q++){const a=(v0+q)*3,b=(v0+(q+1)%n)*3;
      const cr=(P[b]-P[a])*(y-P[a+1])-(P[b+1]-P[a+1])*(x-P[a]);if(cr>1e-6){inside=false;break;}}
    if(inside)best=z;}
  if(best==null){flash('No floor '+(up?'above':'below'));return;}
  flyTo([x,y,best+82],null,null);
}

// ============================================================================
//  Mouse
// ============================================================================
let drag=null, hoverDirty=false, hoverAt=null;
function mods(e){return{shift:e.shiftKey,ctrl:e.ctrlKey||e.metaKey,alt:e.altKey};}
glcv.addEventListener('contextmenu',e=>e.preventDefault());
glcv.addEventListener('mousedown',e=>{
  e.preventDefault();
  if(document.activeElement&&document.activeElement!==document.body&&document.activeElement.blur)document.activeElement.blur();
  drag={b:e.button,x:e.clientX,y:e.clientY,sx:e.clientX,sy:e.clientY,moved:false,m:mods(e)};
  if(e.button===2&&camMode==='rad'){const r=glcv.getBoundingClientRect();radFly={x:e.clientX-r.left,y:e.clientY-r.top};requestDraw();}
});
window.addEventListener('mousemove',e=>{
  const r=glcv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  // the button was let go outside the page: the drag (or Radiant-look's flight) is over
  if(drag&&!(e.buttons&[1,4,2][drag.b])){if(drag.b===2)radFly=null;drag=null;requestDraw();}
  if(drag){
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
    // a wheel pressed down often nudges the mouse, so a middle click gets more slack
    if(Math.abs(e.clientX-drag.sx)+Math.abs(e.clientY-drag.sy)>(drag.b===1?10:4))drag.moved=true;
    if(radFly&&drag.b===2){radFly={x:x,y:y};return;}
    if(!drag.moved||MOD.trim)return;
    if(drag.b===0||drag.b===2){lookBy(dx*0.25,dy*0.25);camChanged();requestDraw();}
    else if(drag.b===1){const a=camAxes(),s=Math.max(0.5,moveSpeed/250);moveBy(a.r,-dx*s);moveBy(a.u,dy*s);camChanged();requestDraw();}
    return;
  }
  if(x>=0&&y>=0&&x<W&&y<H){hoverAt=[x,y];hoverDirty=true;}
});
window.addEventListener('mouseup',e=>{
  if(!drag)return;const d=drag;drag=null;
  if(d.b===2){radFly=null;requestDraw();}
  if(d.moved)return;
  const r=glcv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  if(x<0||y<0||x>=W||y>=H)return;
  if(d.b===0&&ACT.pick){actPickClick(x,y);return;}
  if(d.b===0&&MOD.linking){modLinkClick(x,y);return;}
  if(d.b===0&&!d.m.shift&&!d.m.ctrl&&!d.m.alt&&!MOD.placing&&leakClick(x,y))return;
  if(d.b===0&&MOD.placing){modPlaceClick(x,y);return;}
  if(d.b===0&&!d.m.alt){const mi=modPick(x,y);if(mi>=0){
    if(d.m.shift&&(MOD.sel>=0||MOD.multi.size))modToggleSel(mi);   // Shift+click: into or out of the selection
    else{
      // a plain click selects only it, so the map's selection (brushes, entities) goes, as
      // a plain click on anything does; Shift+click adds it and keeps them
      if(!d.m.shift&&SEL.size){SEL.clear();lastHit=null;selectionChanged();}
      modSelect(mi);if(d.m.ctrl)showInfo('sel');}            // Ctrl+click: and its card
    return;}}
  const h=hitInfo(pickAt(x,y),x,y);
  // a click that picks something else (a brush, a static prop, the sky) lets go of an
  // added entity, as it does of a map entity; Shift+click adds to the selection and
  // Ctrl+Shift+click only reads the face, so they keep it, and so does one being edited,
  // trimmed or moved
  if(d.b===0&&!d.m.shift&&MOD.sel>=0){const cur=MOD.ents[MOD.sel];if(cur&&!modIsMap(cur)&&!modBusy(MOD.sel))modDeselect();}
  // and of the others selected with it (a plain click selects only what it picks)
  if(d.b===0&&!d.m.shift&&MOD.multi.size&&!MOD.trim&&!MOD.placing)MOD.multi.clear();
  if(d.b===0)clickSelect(h,d.m);
  else if(d.b===1)faceInfoAt(h);
});
glcv.addEventListener('dblclick',e=>{if(SEL.size)focusSelection();});
glcv.addEventListener('wheel',e=>{e.preventDefault();if(MOD.trim)return;
  // while the camera follows Simulate's model, the wheel is its camera zoom
  if(SIM.run&&$('simCam').checked){const z=$('simZoom');z.value=Math.max(0,Math.min(100,+z.value+Math.sign(e.deltaY)*(e.shiftKey?10:3)));simZoomShow();return;}
  const a=camAxes();
  moveBy(a.f,-Math.sign(e.deltaY)*(e.shiftKey?256:64));camChanged();requestDraw();},{passive:false});
glcv.addEventListener('mouseleave',()=>{hoverAt=null;setHover(null);updateHoverText(null);});
// hover read-out, a few times a second at most
setInterval(()=>{if(!hoverDirty||!hoverAt||drag||!SC||keys.size||flyAnim||radFly)return;hoverDirty=false;
  const h=hitInfo(pickAt(hoverAt[0],hoverAt[1]),hoverAt[0],hoverAt[1]);modGhost(h);setHover(h);updateHoverText(h);requestDraw();},90);
function updateHoverText(h){
  const el=$('hintHover');if(_flashT&&el.style.color)return;
  if(!h){el.textContent='';return;}
  let s='';
  if(h.face>=0&&(h.ent===0||isWorldlike(h.ent))){const p=SC.prims[h.prim];s=(p.kind===1?'patch ':p.kind===2?'terrain ':'brush ')+p.bn+(h.ent?' ('+MAP.ents[h.ent].cls+')':'')+' · '+(TEX[SC.faceTex[h.face]]||{n:'?'}).n.replace(/^textures\//,'');}
  else s='entity '+h.ent+' · '+entName(h.ent)+(h.face>=0?' · '+(TEX[SC.faceTex[h.face]]||{n:'?'}).n.replace(/^textures\//,''):'');
  if(h.point)s+=' · '+fvec(h.point);
  el.textContent=s;
}
let _txtT=0,_txtTo=0;
function textSoon(){
  const now=performance.now();
  if(now-_txtT>=120){_txtT=now;if(cvEl)cvarWhereRender();updateHint();return;}
  if(!_txtTo)_txtTo=setTimeout(()=>{_txtTo=0;_txtT=performance.now();if(cvEl)cvarWhereRender();updateHint();},130);
}
function updateHint(){
  $('hintCam').textContent=(camMode==='free'?'free-look ':'radiant-look ')+fvec(cam.pos)+'  yaw '+fnum(cam.yaw)+' pitch '+fnum(cam.pitch)+(Math.abs(wrap180(cam.roll))>=0.005?' roll '+fnum(camAngles()[2]):'')+(clipOn?'  clip '+clipDist:'');
}

// ============================================================================
//  Keyboard
// ============================================================================
function typing(){const a=document.activeElement;return a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.tagName==='SELECT');}
const CAM_KEYS_FREE=new Set(['w','a','s','d','q','e','c',' ','arrowup','arrowdown','arrowleft','arrowright']);
const CAM_KEYS_RAD=new Set(['arrowup','arrowdown','arrowleft','arrowright',',','.','d','c','a','z']);
const FILTER_KEYS={'alt+1':C_WORLD,'alt+2':C_ENTITIES,'alt+3':C_PATCH,'alt+4':C_TRANS,'alt+5':C_LIQUID,'alt+6':C_CAULK,
  'alt+7':C_CLIP,'alt+8':C_PATH,'alt+9':C_AINODE,'alt+0':C_LIGHT,'ctrl+d':C_DETAIL,'ctrl+h':C_HINT,'ctrl+m':C_MODEL,
  'ctrl+r':C_TERRAIN,'ctrl+t':C_TRIGGER,'ctrl+p':C_PORTAL,'ctrl+k':C_SKY,'ctrl+o':C_NODRAW,'ctrl+i':C_RAIN,'ctrl+g':C_FOLIAGE,'ctrl+e':C_SCRIPT,'ctrl+b':C_SCRTRIG};
window.addEventListener('keydown',e=>{
  // never the browser's reload or back / forward, even from a text box: they would throw
  // away Modify's work (the launcher turns the pane's own browser keys off too)
  if(e.key==='F5'||e.key==='BrowserRefresh'||e.key==='BrowserBack'||e.key==='BrowserForward'||
     ((e.ctrlKey||e.metaKey)&&(e.key==='r'||e.key==='R'))||(e.altKey&&(e.key==='ArrowLeft'||e.key==='ArrowRight'||e.key==='Home'))){
    e.preventDefault();if(typing()&&!(e.ctrlKey||e.metaKey))return;}
  if(typing()){if(e.key==='Escape'){document.activeElement.blur();e.preventDefault();}return;}
  // MODIFY's Trim origin takes the movement keys: the camera stays where it is
  if(MOD.trim&&!e.ctrlKey&&!e.altKey&&!e.metaKey&&modTrimKey(e)){e.preventDefault();return;}
  const kl=e.key.length===1?e.key.toLowerCase():e.key.toLowerCase();
  // Shift counts with Ctrl or Alt (Ctrl+Shift+X is not Ctrl+X); alone it is part of the key
  // (Shift+G, $)
  const combo=(e.ctrlKey||e.metaKey?'ctrl+':'')+(e.altKey?'alt+':'')+(e.shiftKey&&(e.ctrlKey||e.metaKey||e.altKey)?'shift+':'')
    +(/^digit\d$/i.test(e.code)?e.code.slice(5):kl);
  if(FILTER_KEYS[combo]!=null){toggleFilter(FILTER_KEYS[combo]);e.preventDefault();return;}
  // Ctrl+C over the 3D view (and no text picked out on the page): the point under the
  // cursor, as ( x y z ) for a script
  if(combo==='ctrl+c'&&hoverAt){let t='';try{t=String(window.getSelection()||'');}catch(_e){}
    if(!t){copyCursorPos();e.preventDefault();return;}}
  if(combo==='ctrl+z'){undoHide();e.preventDefault();return;}     // before Radiant-look's Z
  if(combo==='ctrl+a'){showAllGroups();flash('Every group is shown');e.preventDefault();return;}   // and A
  if((e.ctrlKey||e.metaKey)&&kl==='f'){$('findIn').focus();$('findIn').select();e.preventDefault();return;}
  if((e.ctrlKey||e.metaKey)&&(kl==='\\'||e.code==='Backslash')){toggleClip();e.preventDefault();return;}
  // camera keys (held). An auto-repeat of a key the camera has let go of doesn't take it up
  // again, only a new press does: once stopCamera has cleared the keys (the launcher took
  // the mouse or the keyboard), repeats still on their way from the key held then would
  // start the camera again, and its release goes to the launcher.
  const camSet=camMode==='free'?CAM_KEYS_FREE:CAM_KEYS_RAD;
  if(e.key==='Shift'||e.key==='Control'){if(!e.repeat||keys.has(e.key))keys.add(e.key);return;}
  // (Ctrl+W / Ctrl+S in free-look: W and S level with the ground; the other Ctrl chords
  // are left to their own uses)
  if(camSet.has(kl)&&!e.altKey&&!(e.ctrlKey&&camMode==='free'&&kl!=='w'&&kl!=='s')){
    if(camMode==='rad'&&e.ctrlKey){if(['arrowup','arrowdown',',','.'].includes(kl)){gridStep(kl);e.preventDefault();}return;}
    if(!e.repeat||keys.has(kl))keys.add(kl);
    e.preventDefault();return;}
  // Alt+C Copy, Alt+Z Undo, Alt+Y / Alt+Shift+Z Redo: Modify's buttons, as clicked
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&(kl==='c'||kl==='z'||kl==='y')){
    const id=kl==='c'?'bModDup':(kl==='y'||e.shiftKey)?'bModHRedo':'bModHUndo',b=$(id);
    if(b&&!b.disabled)b.click();else if(kl!=='c')flash(id==='bModHUndo'?'Nothing to undo in Modify':'Nothing to redo in Modify');
    else flash('Select what to copy first (Shift+click adds more)');
    e.preventDefault();return;}
  // Alt+A Add: Modify's Add, as clicked (again cancels the placing)
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&kl==='a'){const b=$('bModAdd');if(b&&!b.disabled)b.click();e.preventDefault();return;}
  // Alt+M Move, Alt+T Trim origin, Alt+R Yaw, Alt+E Edit parameters, Alt+S Spawnflags:
  // Modify's buttons for its selected entity (as clicked, so not while one is off)
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&(kl==='m'||kl==='t'||kl==='r'||kl==='e'||kl==='s')){
    const b=$({m:'bModMove',t:'bModTrim',r:'bModYaw',e:'bModEdit',s:'bModSf'}[kl]);
    if(MOD.sel<0)flash('Select an entity in Modify first (Alt+M Move, Alt+T Trim origin, Alt+R Yaw, Alt+E Edit parameters, Alt+S Spawnflags)');
    else if(!b.disabled)b.click();
    e.preventDefault();return;}
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  if(e.code==='Backquote'){toggleCvarMenu();e.preventDefault();return;}   // as the game's console key
  switch(kl){
    case 'h':case '?':if(e.shiftKey&&kl==='h'){const had=hidEnt.size+hidPrim.size;unhideAll();
      flash(had?'Everything is shown again (Ctrl+Z hides it again)':'Nothing is hidden');}else toggleHelp();break;
    case 'n':showInfo('sel');break;
    case 'g':if(e.shiftKey){editorLook();flash('Editor look');}else{gameLook();flash('In-game look');}break;
    case 'b':toggleFullBright();break;
    case 'k':toggleSimpleSky();break;
    case 'm':toggleSimpleModels();break;
    case 'j':toggleSunFlare();break;
    case 'i':if($('bRoutes').disabled)flash($('bRoutes').title);else $('bRoutes').click();break;   // AI routes (ai_showroutes)
    case 'f':focusSelection();break;
    case '+':setGrid(!GRID.on);break;
    case '{':setGridSize(GRID.i-1);break;
    case '}':setGridSize(GRID.i+1);break;
    case '$':selectSameTargetname(selFocusEnt());break;     // Shift+4: $targetname
    case 'o':doorUse();break;
    case 'v':setCamMode(camMode==='free'?'rad':'free');break;
    case 'r':resetCam();break;
    case 'x':stopCamera();flash('Camera stopped');break;
    case 'l':toggleLegend();break;
    case 't':themeBtn.click();break;
    // U levels the view (no pitch, no tilt). Not End: in a browser End scrolls whatever has
    // the focus to its end, so the side panel would jump to its bottom.
    case 'u':cam.pitch=0;cam.roll=0;camChanged();requestDraw();break;
    case 'pageup':changeFloor(true);e.preventDefault();break;
    case 'pagedown':changeFloor(false);e.preventDefault();break;
    case '[':setClipDist(clipDist-256);if(!clipOn)toggleClip();break;
    case ']':setClipDist(clipDist+256);if(!clipOn)toggleClip();break;
    // Backspace hides, Delete removes an entity added in Modify (selected in the view or its
    // list), as its Hide square and Delete button do; Backspace also hides the map's selection
    case 'backspace':{const m=MOD.ents[MOD.sel];
      if(m&&!modIsMap(m)&&!m.hid){const i=MOD.sel;modToggleHide(i);if(MOD.ents[i]&&MOD.ents[i].hid)modDeselect();}
      if(SEL.size)hideSelection();e.preventDefault();break;}
    case 'delete':{const Ln=modSelEnts(false).filter(x=>!x.del);
      if(Ln.length){const nm=Ln.length===1?modName(Ln[0]):Ln.length+' entities';modRemoveSel();MOD.sel=-1;MOD.multi.clear();modRender();requestDraw();
        flash('Deleted: '+nm+' (not saved yet; Undo, Alt+Z, puts it back)');}
      else if(SEL.size)flash('Select the map entity in Modify first (it needs a MODIFY row): Delete flags it DEL');
      e.preventDefault();break;}
    case '/':$('findIn').focus();e.preventDefault();break;
    case '\\':case '|':$('sideTab').click();e.preventDefault();break;
    case 'escape':escape();break;
    default:{const d=DISPLAY.find(x=>x.key===e.key||x.key.toLowerCase()===kl);if(d){toggleDisplay(d.k);}}
  }
});
window.addEventListener('keyup',e=>{const kl=e.key.length===1?e.key.toLowerCase():e.key;keys.delete(kl);keys.delete(kl.toLowerCase());
  if(e.key==='Shift'||e.key==='Control')keys.delete(e.key);});
// Stop every movement: held keys, a drag, Radiant-look's right-button flight, a fly-to.
// X does it by hand. It also happens when the page loses the keyboard or the window, since
// a key or button let go elsewhere never reaches the page (in the launcher's pane a click
// on the launcher itself also calls this), and each frame while the page doesn't have the
// focus (see loop).
function stopCamera(){keys.clear();radFly=null;drag=null;flyAnim=null;requestDraw();}
// Let go of the held keys only; a drag, Radiant-look's flight and a fly-to go on. The launcher
// calls this when the keyboard went elsewhere: a key pressed or let go in the launcher, or the
// last camera key let go while the page wasn't listening (App._watch_camera_stop).
function releaseCameraKeys(){if(keys.size){keys.clear();requestDraw();}}
// A right-click that opens the browser's own menu (anywhere but the 3D view, whose right
// button flies and looks): the menu takes the keyboard while it is open, so a key let go
// then never reaches the page and the camera flew on. It stops as the menu opens.
window.addEventListener('contextmenu',e=>{if(!e.defaultPrevented)stopCamera();});
window.addEventListener('blur',stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCamera();});
// Ctrl + arrows / comma / period in Radiant-look: one grid step (MOHRadiant's CameraGrid* commands).
function gridStep(kl){const a=camAxes(),g=64;const flat=vnorm([a.f[0],a.f[1],0])||[1,0,0];
  if(kl==='arrowup')moveBy(flat,g);else if(kl==='arrowdown')moveBy(flat,-g);
  else if(kl===',')moveBy(a.r,-g);else if(kl==='.')moveBy(a.r,g);
  camChanged();requestDraw();}
// Esc peels one layer at a time: help or legend, info card, selection, then the map itself.
function escape(){
  if($('simOv').style.display!=='none'){simClose();return;}
  if(ACT.pick){actPickCancel();return;}
  if(MOD.placing){modPlaceCancel();return;}
  if(MOD.linking){modLinkCancel();return;}
  if(MOD.edit>=0){modEditClose(true);return;}
  if(MOD.trim){modTrim(false);return;}
  if(helpOv.style.display!=='none'){toggleHelp(false);return;}
  if(legOv.style.display!=='none'){toggleLegend(false);return;}
  if($('info').classList.contains('on')){hideInfo();return;}
  if(MOD.sel>=0){modDeselect();return;}
  if(SEL.size){SEL.clear();selectionChanged();return;}
  closeViewer();
}

// ============================================================================
//  Side panel
// ============================================================================
const DISPLAY=[
 {k:'tex',l:'Texture',key:'1',t:'Textures on (off = each texture\'s average colour)'},
 {k:'shade',l:'Shade',key:'2',t:'MOHRadiant\'s face shading: walls facing different ways get slightly different brightness, so shapes read without lighting (for Full Brightness and the editor-only surfaces)'},
 {k:'wire',l:'Wire',key:'3',t:'Outline every brush face, patch and terrain block'},
 {k:'ss',l:'Setsizes',key:'4',t:'The bounding box of every entity (origin + setsize). The selection always shows its own.'},
 {k:'arrows',l:'Arrows',key:'5',t:'Which way entities with an angle face (player starts, nodes...): a white arrow, as MOHRadiant draws it'},
 {k:'labels',l:'Labels',key:'6',t:'Class and $targetname over nearby entities'},
 {k:'links',l:'Links',key:'7',t:'A line from each entity to the entities its "target" key points at'},
 {k:'fog',l:'Fog',key:'8',t:'The map\'s distance fog (worldspawn farplane / farplane_color), like in game'},
 {k:'xray',l:'X-ray',key:'9',t:'Show the selection\'s outline, box, target links and facing arrow faintly through walls (everything else stays hidden behind them). Off, labels and path tags don\'t show through walls either: only those whose spot the camera can see'},
 {k:'lights',l:'Lights off',key:'0',t:'Every light entity of the map off, as if it had never been there: the game\'s baked light (lightmaps, vertex light, props and models) keeps only what the sun, the sky and the ambient light give it. Again: every light back on. Single lights turn off and on from Selection (Turn off / Turn on). The first time takes a moment, while the page works out how much of the baked light each light gave'},
 {k:'sun',l:'Sun light',key:'-',t:'The sun\'s and the sky\'s light on the map (worldspawn suncolor, sundirection, sundiffuse). Off: the game\'s baked light (lightmaps, vertex light, props and models) keeps only what the lights and the ambient light give it, so open ground goes dark. The sun flare (J) is separate. The first time takes a moment, as Lights off does'},
 {k:'grid',l:'Grid',key:'+',t:'Grid: a see-through grid of MOHRadiant\'s grid size round what you work on (Modify\'s selected or moving entity, else the surface ahead of the camera), with its coordinates counted from ( 0 0 0 ). While it is on, Add and Move in Modify snap to it, as MOHRadiant snaps to its grid. Under the backdrop: which planes (Grid XY / XZ / YZ / all), the size ({ and }) and its colour'},
 {k:'decals',l:'Decals',key:'=',t:'The map\'s permanent decals (its .dcl: signs, cracks, numbers placed in MOHRadiant), as the game draws them, lit by the colour the file keeps (white with Full Brightness)'},
 {k:'weather',l:'Weather',key:'Y',t:'The game\'s rain and snow (cg_rain): drops start in the map\'s func_rain boxes near you as the client makes them, with the map\'s settings (its script\'s level.rain_*). The game cvars (`) have every setting: cg_weather snow / rain / blizzard ..., density, speed, size, shader, the client\'s frame rate'},
 {k:'leak',l:'Leak',key:'P',t:'The compiler\'s leak trail (the map\'s .lin): a red line through walls from the void outside the map to the entity it reaches, with a light blue circle where it gets in (the gap to fix). On: its card says where and how to fix it, with Go buttons; a click on the trail opens it'}];
const FILTERS=[
 {m:C_WORLD,l:'World',key:'Alt+1',t:'Structural world brushes'},
 {m:C_ENTITIES,l:'Entities',key:'Alt+2',t:'Every entity: brush entities, models, lights, nodes, markers'},
 {m:C_PATCH,l:'Patches',key:'Alt+3',t:'Curved patch meshes'},
 {m:C_TRANS,l:'Translucent',key:'Alt+4',t:'See-through surfaces: glass, decals, effects'},
 {m:C_LIQUID,l:'Liquids',key:'Alt+5',t:'Water, slime, lava and fog volumes'},
 {m:C_CAULK,l:'Caulk',key:'Alt+6',t:'common/caulk faces the game never draws'},
 {m:C_CLIP,l:'Clips',key:'Alt+7',t:'Player, monster, weapon and vehicle clips (common/*clip)'},
 {m:C_PATH,l:'Paths',key:'Alt+8',t:'Spline paths and waypoints'},
 {m:C_AINODE,l:'AI nodes',key:'Alt+9',t:'info_pathnode navigation nodes, coloured as in MOHRadiant (a node\'s info card explains its colours)'},
 {m:C_LIGHT,l:'Lights',key:'Alt+0',t:'light entities'},
 {m:C_DETAIL,l:'Details',key:'Ctrl+D',t:'Detail brushes'},
 {m:C_HINT,l:'Hints',key:'Ctrl+H',t:'Hint and skip brushes'},
 {m:C_MODEL,l:'Models',key:'Ctrl+M',t:'Every entity drawn with a model'},
 {m:C_TERRAIN,l:'Terrain',key:'Ctrl+R',t:'LOD terrain blocks'},
 {m:C_TRIGGER,l:'Triggers',key:'Ctrl+T',t:'trigger_* entities and common/trigger brushes'},
 {m:C_PORTAL,l:'Areaportals',key:'Ctrl+P',t:'Areaportal brushes'},
 {m:C_SKY,l:'Sky',key:'Ctrl+K',t:'Sky brushes: show or hide them completely (with them hidden, whatever is behind shows, else the backdrop)'},
 {m:C_NODRAW,l:'Nodraw',key:'Ctrl+O',t:'Other editor-only surfaces: nodraw, ladders, patharea, and the flat tree pictures that only cast a tree\'s shadow (misc_outside/commontreeshadow)'},
 {m:C_RAIN,l:'Rain',key:'Ctrl+I',t:'common/rain: the volumes of func_rain entities, where rain or snow falls in game. Hidden until you show them'},
 {m:C_FOLIAGE,l:'Foliage clips',key:'Ctrl+G',t:'common/foliageclip: walk-through brushes around trees and bushes that make foliage effects when shot'},
 {m:C_ORIGIN,l:'Origin',key:'',t:'common/origin brushes (the pivot of doors and movers)'},
 {m:C_POINT,l:'Point ents',key:'',t:'Other point entities: player starts, script origins, info_* ...'},
 {m:C_SCRIPT,l:'Script ents',key:'Ctrl+E',t:'Entities the map\'s level script spawns (spawn lines in its .scr), placed where its lines say: waypoints, script models and origins, actors... They are drawn as their kind (a waypoint with the Paths, a model with the Models) and this hides them all. The map\'s stats line opens the list'},
 {m:C_SCRTRIG,l:'Script trigs',key:'Ctrl+B',t:'The volumes of the triggers the map\'s level script spawns, from their setsize (worked out from its lines, its own fields such as local.t.setsize1 included): see-through boxes in the trigger colour, as trigger brushes look. Script ents shows the triggers themselves as small markers; selecting one outlines its volume. Hidden by the In-game look'}];
// The entity kinds the Entities button (Alt+2) covers, named for its tooltip when only
// some of them are hidden (by their own buttons).
const ENT_PARTS=[[C_ENTBRUSH,'brush entities'],[C_POINT,'point ents'],[C_LIGHT,'lights'],[C_AINODE,'AI nodes'],
  [C_PATH,'paths'],[C_MODEL,'models'],[C_STATIC,'static props'],[C_VIS,'vis']];
function buildPanel(){
  const db=$('dispBtns');
  for(const d of DISPLAY){const b=document.createElement('button');b.id='d_'+d.k;b.innerHTML=esc(d.l)+'<span class="k">'+d.key+'</span>';
    b.title=d.t+' ('+d.key+')';b.onclick=()=>toggleDisplay(d.k);db.appendChild(b);}
  // Lights off and Sun light need a .bsp's baked light (ltCheck says why not), Sun light a sun
  if(!ltCheck()){for(const k of ['lights','sun']){$('d_'+k).disabled=true;$('d_'+k).title=LT.why;}}
  else if(!LT.sunHas){$('d_sun').disabled=true;$('d_sun').title=LT.sunWhy;}
  if(!dclHas()){$('d_decals').disabled=true;$('d_decals').title=dclWhy();}
  else $('d_decals').title+='\n'+D.dcl.n+' decal'+(D.dcl.n===1?'':'s')+' ('+D.dcl.nf+' fragments) from '+D.dcl.src;
  if(!leakHas()){$('d_leak').disabled=true;$('d_leak').title=leakWhy();}
  else $('d_leak').title+='\n'+D.leak.p.length+' points from '+D.leak.src;
  const fb=$('filtBtns');
  for(const f of FILTERS){const b=document.createElement('button');b.innerHTML=esc(f.l)+(f.key?'<span class="k">'+f.key+'</span>':'');
    b.title=f.t+(f.key?' ('+f.key+')':'')+' - click to show / hide';f.el=b;b.onclick=()=>toggleFilter(f.m);fb.appendChild(b);}
  fb.appendChild($('bRoutes'));          // AI routes, AI errors and All go last, after Origin and Point ents
  fb.appendChild($('bAiErr'));
  fb.appendChild($('bShowAll'));
  $('bFull').onclick=toggleFullBright;
  if(!LIT){$('bFull').disabled=true;
    $('bFull').title=D.kind==='bsp'?'This .bsp has no lightmaps, so the game draws it at full brightness too.'
      :'A .map has no lighting yet: the game\'s light is baked when the map is compiled. Open the compiled .bsp to see it.';}
  $('bSimpleSky').onclick=toggleSimpleSky;
  $('bSimpleMod').onclick=toggleSimpleModels;
  $('bSunFlare').onclick=toggleSunFlare;
  $('bRoutes').onclick=()=>{setCvar('ai_showroutes',CVARS.ai_showroutes?0:1);syncButtons();
    flash(CVARS.ai_showroutes?'AI routes on (ai_showroutes 1): '+routesFrom():'AI routes off (ai_showroutes 0)');};
  AIERR=TRACEPATH=!!CVARS.ai_showroutes;
  $('bAiErr').onclick=()=>{AIERR=!AIERR;syncButtons();requestDraw();
    flash(AIERR?'AI errors shown: no paths, one-way, own group, in the wall, no angle':'AI errors hidden');};
  if(!routesOk()){$('bRoutes').disabled=true;$('bRoutes').title='This map has no AI paths (no .pth file in the paks, or one the viewer couldn\'t read): ai_showroutes has nothing to draw';}
  if(!sunHas()){$('bSunFlare').disabled=true;$('bSunFlare').title=sunNone();}
  $('bShowAll').onclick=showAllGroups;$('bGameView').onclick=gameLook;$('bEditView').onclick=editorLook;
  $('cvarBtn').onclick=ev=>{ev.stopPropagation();toggleCvarMenu();};
  syncButtons();
  $('bFree').onclick=()=>setCamMode('free');$('bRad').onclick=()=>setCamMode('rad');
  const sp=$('speed');sp.value=moveSpeed;$('speedV').textContent=moveSpeed;sp.oninput=()=>{moveSpeed=+sp.value;$('speedV').textContent=moveSpeed;saveOpts();};
  const fv=$('fov');fv.value=fovX;$('fovV').textContent=fovX;fv.oninput=()=>{fovX=+fv.value;$('fovV').textContent=fovX;saveOpts();requestDraw();};
  const cd=$('clipD');cd.value=clipDist;$('clipV').textContent=clipDist;cd.oninput=()=>setClipDist(+cd.value);
  $('bClip').onclick=toggleClip;$('bClip').classList.toggle('on',clipOn);
  $('gotoIn').addEventListener('keydown',e=>{if(e.key!=='Enter')return;const v=vecNums($('gotoIn').value);
    if(v.length>=3){flyTo([v[0],v[1],v[2]],null,null);$('gotoIn').blur();}else flash('Type three numbers: x y z');});
  $('bCopyCam').onclick=()=>{const t=fvec(cam.pos);copyText(t,'Camera\'s origin '+t+' copied to the clipboard');};
  $('angIn').addEventListener('keydown',e=>{if(e.key!=='Enter')return;const v=vecNums($('angIn').value);
    if(v.length>=3){turnTo(v[0],v[1],v[2]);$('angIn').blur();}else flash('Type three numbers: pitch yaw roll');});
  $('bCopyAng').onclick=()=>{const t=fvec(camAngles());copyText(t,'Camera\'s angles '+t+' copied to the clipboard');};
  $('bInfo').onclick=()=>showInfo('sel');$('bFocus').onclick=focusSelection;$('bHide').onclick=hideSelection;
  $('bClear').onclick=()=>{SEL.clear();selectionChanged();};$('bUnhide').onclick=unhideAll;$('bUndoHide').onclick=undoHide;
  $('bSame').onclick=()=>{if(lastHit)selectSameKind(lastHit,false);};
  $('bSameSf').onclick=()=>selectSameSpawnflags(selFocusEnt());
  $('bSameErr').onclick=selectSameError;
  $('bEye').onclick=()=>{const ei=+$('bEye').dataset.ei,v=ei>0?eyeView(ei):null;if(!v)return;
    flyTo(v.pos,v.ang[1],v.ang[0],-v.ang[2]);requestDraw();flash(v.flash);};
  $('bPath').onclick=()=>{const ei=+$('bPath').dataset.ei;if(ei>0)selectPath({ent:ei,face:-1,prim:-1,point:null},false);};
  $('bTname').onclick=()=>selectSameTargetname(selFocusEnt());
  $('bDoor').onclick=doorUse;
  $('bExpRun').onclick=expRunSel;$('bExpReset').onclick=()=>expReset();
  $('bLightOff').onclick=()=>setSelLights(false);$('bLightOn').onclick=()=>setSelLights(true);
  $('infoClose').onclick=hideInfo;$('infoScr').onclick=()=>openScr(0);$('infoCopy').onclick=()=>copyText($('infoBody').innerText);
  $('tabFind').onclick=()=>setTab('find');$('tabCls').onclick=()=>setTab('cls');$('tabTex').onclick=()=>setTab('tex');
  $('tabEnt').onclick=()=>setTab('ent');
  const fi=$('findIn');let ft=null;
  fi.addEventListener('input',()=>{clearTimeout(ft);ft=setTimeout(()=>{setTab('find');},150);});
  fi.addEventListener('keydown',e=>{if(e.key==='Enter'){setTab('find');selectFindResults();e.preventDefault();}});
}
// All (Ctrl+A), In-game look (G) and Editor look (Shift+G). The two looks also set the light
// and the sky: MOHRadiant is always full bright.
function showAllGroups(){hiddenMask=0;filtersChanged();}
const GAME_LOOK=C_CAULK|C_CLIP|C_TRIGGER|C_HINT|C_ORIGIN|C_PORTAL|C_NODRAW|C_POINT|C_LIGHT|C_AINODE|C_PATH|C_VIS|C_RAIN|C_FOLIAGE|C_SCRTRIG,
  EDIT_LOOK=C_HINT|C_PORTAL|C_RAIN;
function gameLook(){hiddenMask=GAME_LOOK;simpleSky=false;fullBright=false;setSunFlare(true);filtersChanged();requestDraw();}
function editorLook(){hiddenMask=EDIT_LOOK;simpleSky=true;fullBright=true;setSunFlare(false);filtersChanged();requestDraw();}
// a look's sun flare setting counts only on a map that has a flare
function flareAs(on){return !sunHas()||sunFlare===on;}
function syncButtons(){
  for(const d of DISPLAY){const b=$('d_'+d.k);if(b&&d.k!=='lights'&&d.k!=='sun'&&d.k!=='weather'&&d.k!=='grid')b.classList.toggle('on',!!view[d.k]&&!b.disabled);}
  {const b=$('d_grid');if(b)b.classList.toggle('on',GRID.on);}
  {const b=$('d_weather');if(b){b.classList.toggle('on',!!CVARS.cg_rain);
    b.classList.toggle('part',!!CVARS.cg_rain&&(!(+CVARS.cg_rain_density>0)||(!WX.rainEnts.length&&!CVARS.cg_rain_wholemap&&!wxSkyBrushes().length)));}}
  {const b=$('d_sun');if(b)b.classList.toggle('on',LT.ok?(LT.sunHas&&!LT.sunOff):false);}
  // Lights off: on while every light is off, dashed while only some are
  {const b=$('d_lights');if(b){const n=LT.off?LT.off.reduce((a,x)=>a+x,0):0,all=LT.off&&n===LT.off.length&&n>0;
    b.classList.toggle('on',!!all);b.classList.toggle('part',n>0&&!all);
    if(LT.ok)b.title=DISPLAY.find(d=>d.k==='lights').t+' (0)'+(n>0&&!all?'\nNow: '+n+' of '+LT.off.length+' lights off':'')+
      (LT.crash?'\nThe last time lights were turned off on this map, the graphics driver reset ('+LT.crash.step+'): the first press only warns.':'');}}
  // A button is on while what it covers is shown. Entities covers several kinds that have
  // buttons of their own (AI nodes, Lights, Models, Paths, Point ents): with only some of
  // them hidden it stays on, dashed, and its tooltip says which are hidden.
  for(const f of FILTERS){const hid=hiddenMask&f.m, part=!!hid&&hid!==f.m;
    f.el.classList.toggle('on',!hid||part);f.el.classList.toggle('part',part);
    f.el.title=f.t+(f.key?' ('+f.key+')':'')+' - click to show / hide'+
      (part?'\nSome hidden: '+ENT_PARTS.filter(x=>hid&x[0]).map(x=>x[1]).join(', ')+' (a click hides the rest, a second shows all)':'');}
  $('bFull').classList.toggle('on',fullBright||!LIT);
  $('bSimpleSky').classList.toggle('on',simpleSky);
  $('bSimpleMod').classList.toggle('on',simpleModels);
  $('bSunFlare').classList.toggle('on',sunFlare&&sunHas());
  $('bRoutes').classList.toggle('on',!!CVARS.ai_showroutes&&routesOk());
  $('bAiErr').classList.toggle('on',AIERR);
  // a look is on while everything it sets is still as it set it
  $('bGameView').classList.toggle('on',hiddenMask===GAME_LOOK&&!simpleSky&&!fullBright&&flareAs(true));
  $('bEditView').classList.toggle('on',hiddenMask===EDIT_LOOK&&simpleSky&&fullBright&&flareAs(false));
  $('bFree').classList.toggle('on',camMode==='free');$('bRad').classList.toggle('on',camMode==='rad');
  $('camHelpFree').style.display=camMode==='free'?'':'none';$('camHelpRad').style.display=camMode==='rad'?'':'none';
}
function toggleDisplay(k){if(k==='grid'){setGrid(!GRID.on);return;}if(k==='lights'){toggleLightsOff();return;}if(k==='sun'){toggleSunLight();return;}if(k==='weather'){toggleWeather();return;}
  view[k]=!view[k];syncButtons();saveOpts();
  if(k==='wire'&&view.wire)rebuildWire();
  if(k==='fog'&&view.fog&&!FOG.far)flash('This map has no farplane fog');
  if(k==='decals')flash(!dclHas()?dclWhy():view.decals?'Decals on: '+D.dcl.n+' from '+D.dcl.src:'Decals off');
  if(k==='leak'){if(!leakHas())flash(leakWhy());else if(view.leak){leakCard();flash('Leak trail on: the red line runs from the void to the entity it reaches; the light blue circle is where it gets in');}
    else{if(infoMode==='leak')hideInfo();flash('Leak trail off');}}
  lineDirty=true;requestDraw();}
function toggleFilter(m){if((hiddenMask&m)===m)hiddenMask&=~m;else hiddenMask|=m;filtersChanged();}
function toggleSimpleSky(){
  simpleSky=!simpleSky;
  if(simpleSky&&sunFlare)setSunFlare(false);    // MOHRadiant's tiled sky has no sun to flare
  syncButtons();saveOpts();requestDraw();
  flash(simpleSky?'Simple Sky: the sky brushes tiled and solid (as MOHRadiant)':'The game\'s sky, behind everything');}
function toggleSimpleModels(){
  simpleModels=!simpleModels;syncButtons();saveOpts();requestDraw();
  const n=MODELS.filter(R=>R.hasLod&&R.inst.length).length;
  flash(simpleModels?(n?'Simple models: trees drawn as their sprite version, as the game draws them far away'
    :'Simple models on: no model in this map has a sprite version'):'Simple models off: the whole trees');}
function toggleFullBright(){
  if(!LIT){flash(D.kind==='bsp'?'This .bsp has no lightmaps':'A .map has no compiled lighting - open the .bsp');return;}
  fullBright=!fullBright;syncButtons();saveOpts();requestDraw();
  flash(fullBright?'Full Brightness on (as MOHRadiant)':'The game\'s own lighting');}
function toggleSunFlare(){
  if(!sunHas()){flash(sunNone());return;}
  setSunFlare(!sunFlare);syncButtons();saveOpts();requestDraw();
  flash(sunFlare?'Sun flare on: the game\'s flare when you look toward the sun':'Sun flare off');}
function filtersChanged(){syncButtons();saveOpts();rebuildWorld();updateSelPanel();}
function setCamMode(m){camMode=m;keys.clear();radFly=null;syncButtons();saveOpts();requestDraw();}
function setClipDist(v){clipDist=Math.max(128,Math.min(32768,v));$('clipD').value=clipDist;$('clipV').textContent=clipDist;saveOpts();requestDraw();}
function toggleClip(){clipOn=!clipOn;$('bClip').classList.toggle('on',clipOn);saveOpts();requestDraw();}
function saveOpts(){slidersPost();const cv={};for(const k of cvarsSet())if(!CVAR_NOSAVE.has(k))cv[k]=CVARS[k];
  LS.set('mohaaMapViewerOpts',JSON.stringify({ov:2,view:view,hidden:hiddenMask,mode:camMode,speed:moveSpeed,fov:fovX,clip:clipOn,clipD:clipDist,fb:fullBright,ss:simpleSky,sm:simpleModels,sf:sunFlare,cv:cv}));}
function loadOpts(){try{const o=JSON.parse(LS.get('mohaaMapViewerOpts')||'null');if(!o)return;
  for(const k in view)if(k in (o.view||{}))view[k]=!!o.view[k];
  fullBright=!!o.fb;simpleSky=!!o.ss;simpleModels=!!o.sm;
  if('sf' in o)sunFlare=!!o.sf;                  // options saved before the Sun flare button: on
  if(typeof o.hidden==='number')hiddenMask=o.hidden;if(o.mode==='rad'||o.mode==='free')camMode=o.mode;
  // options saved before Rain had a button of its own: it starts hidden, as on a first visit
  if(!(o.ov>=2))hiddenMask|=C_RAIN;
  // static models have no Show button of their own (Models and Entities hide them)
  if((hiddenMask&C_ENTITIES)!==C_ENTITIES)hiddenMask&=~C_STATIC;
  if(o.speed>0)moveSpeed=o.speed;if(o.fov>0)fovX=Math.max(60,Math.min(150,o.fov));clipOn=!!o.clip;if(o.clipD>0)clipDist=o.clipD;
  for(const k in (o.cv||{}))if(k in CVAR_DEFAULTS){const v=cvarClamp(k,o.cv[k]);if(v!=null)CVARS[k]=v;}}catch(_e){}}

function updateSelPanel(){
  simPanel();
  const n=SEL.size;$('selBtns').style.display=n?'':'none';
  const hid=hidEnt.size+hidPrim.size;$('hidLine').style.display=(hid||HIDE_UNDO.length)?'':'none';
  $('hidCount').textContent=hid+' hidden';$('bUndoHide').disabled=!HIDE_UNDO.length;$('bUnhide').disabled=!hid;
  const el=$('selSum');
  if(!n){el.textContent='Click anything in the map to select it.';el.className='co';return;}
  el.className='';
  const ents=[...selectedEnts()], prims=selectedPrims();
  // Same path: the path through the one selected entity (else the last one clicked), when
  // its "target" leads somewhere or something targets it (as Ctrl+Alt+click)
  const pe=selFocusEnt();
  const pp=(pe>0&&!isWorldlike(pe))?pathOf(pe):null;
  $('bPath').style.display=(pp&&(pp.before.size||pp.after.size))?'':'none';$('bPath').dataset.ei=pe;
  // Eye view: an entity that faces somewhere (angles, or a target to look at)
  const ev=(pe>0&&!isWorldlike(pe))?eyeView(pe):null;
  $('bEye').style.display=ev?'':'none';$('bEye').dataset.ei=pe;
  if(ev)$('bEye').title=ev.why;
  // Same spawnflags: greyed out unless the one selected entity has spawnflags
  {const sf=sfOf(pe);$('bSameSf').disabled=!sf;
    $('bSameSf').title=sf?'Select every '+MAP.ents[pe].cls+' with spawnflags '+sf:'Select every entity of the same class with the same spawnflags (the selected entity has none)';}
  // Same error: greyed out unless at least one selected path node has an error
  {const b=$('bSameErr'),e=selNodeErrors();b.disabled=!(e&&e.kinds.size);
    b.title=(e&&e.kinds.size)?'Select every path node with '+(e.kinds.size>1?'any of these errors':'this error')+': '+[...e.kinds.values()].join(', '):'Select every path node with the same error as the selected path node(s): none of the selected path nodes has an error';}
  // Same targetname: when other entities share its targetname
  const tn=(pe>0&&!isWorldlike(pe))?MAP.ents[pe].kvl.targetname:'', tl=tn?(ENTS.tn.get(tn)||[]):[];
  $('bTname').style.display=tl.length>1?'':'none';
  if(tl.length>1)$('bTname').title='Select every entity named $'+tn+': '+tl.length+' of them ($, that is Shift+4)';
  // Open door / Close door: when a door is selected
  doorBtnRender();
  // Run exploder / Reset exploder: when an exploder's entity is selected
  expBtnRender();
  // Turn off / Turn on: when lights are selected (greyed out where there is no baked light)
  {const lights=ents.filter(ei=>String(MAP.ents[ei].cls).startsWith('light'));
    $('bLightOff').style.display=$('bLightOn').style.display=lights.length?'':'none';
    if(lights.length){const ok=ltCheck(), offN=ok?lights.filter(ei=>ltLightOff(ei)).length:0;
      $('bLightOff').disabled=!ok||offN===lights.length;$('bLightOn').disabled=!ok||offN===0;
      if(!ok)$('bLightOff').title=$('bLightOn').title=LT.why;
      else{$('bLightOff').title='Turn the selected light'+(lights.length>1?'s':'')+' off, as if '+(lights.length>1?'they':'it')+' had never been there: the light '+(lights.length>1?'they':'it')+' gave the map (its lightmaps, vertex light, props and models) goes, the rest stays. Display\'s Lights off turns every light off'+(offN?'\nNow: '+offN+' of '+lights.length+' off':'');
        $('bLightOn').title='Turn the selected light'+(lights.length>1?'s':'')+' back on';}}}
  let s='';
  if(n===1&&ents.length===1){const ei=ents[0],e=MAP.ents[ei],X=ENTS[ei];
    s=e.kvl.classname+(e.kvl.targetname?'  $'+e.kvl.targetname:'')+'\nentity '+ei;
    if(X.box)s+='\norigin '+fvec(X.box.origin)+'\nsetsize '+fvec(X.box.mins)+' '+fvec(X.box.maxs)+(X.box.exact?'':'  (approx.)');}
  else if(n===1&&prims.length===1){const p=SC.prims[prims[0]];
    s=(p.kind===1?'patch ':p.kind===2?'terrain ':'brush ')+p.bn+' of '+(p.ent?('entity '+p.ent+' ('+MAP.ents[p.ent].cls+')'):'the world')+
      '\nsize '+fvec([p.maxs[0]-p.mins[0],p.maxs[1]-p.mins[1],p.maxs[2]-p.mins[2]])+'\ncentre '+fvec([(p.mins[0]+p.maxs[0])/2,(p.mins[1]+p.maxs[1])/2,(p.mins[2]+p.maxs[2])/2]);}
  else{s=n+' selected';if(ents.length)s+=' · '+ents.length+' entit'+(ents.length===1?'y':'ies');if(prims.length)s+=' · '+prims.length+' brush'+(prims.length===1?'':'es');
    const b=selBounds();if(b)s+='\nbounds '+fvec(b.mins)+' '+fvec(b.maxs);
    if(ents.length===2&&!prims.length){const A=ENTS[ents[0]].anchor,Bb=ENTS[ents[1]].anchor;if(A&&Bb)s+='\ndistance between them: '+fnum(Math.hypot(A[0]-Bb[0],A[1]-Bb[1],A[2]-Bb[2]));}}
  el.textContent=s;
}

// ---- find / classes / textures lists -----------------------------------------------------
let curTab='find', findRes=[];
function setTab(t){curTab=t;for(const[id,k]of[['tabFind','find'],['tabCls','cls'],['tabTex','tex'],['tabEnt','ent']])$(id).classList.toggle('on',k===t);renderList();}
let SEARCH=null;
function searchText(ei){if(!SEARCH)SEARCH=MAP.ents.map(e=>e.kv.map(kv=>kv[0]+' '+kv[1]).join(' \u0001 ').toLowerCase());return SEARCH[ei];}
// The search box, a little like a web search. Terms are ANDed; each can start with "-" to
// leave out what it matches:
//   word              any key or value (or texture name) that contains it
//   "a phrase"        a key value (or texture name) that is exactly that
//   $name             targetname exactly name
//   key:              an entity that has that key at all ("#set:", "-target:")
//   key: value        that key exactly that value ("classname: exploder", "#set: 4",
//                     "texture: x", "entity: 25", "entnum: 104"); * matches any run of letters
//   entity 25         the viewer's entity 25 (as Selection numbers them)
//   ( x y z )         an entity whose origin is exactly there
function findTerms(q){
  const T=[],re=/(-?)(?:"([^"]*)"?|\(\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)|([^\s:"]+)\s*:\s*(?:"([^"]*)"?|([^\s"]*))|(\S+))/g;
  let m;
  while((m=re.exec(q))){
    const neg=m[1]==='-';
    if(m[2]!=null){if(m[2].trim())T.push({k:'exact',v:m[2].trim().toLowerCase(),neg:neg});}
    else if(m[3]!=null)T.push({k:'org',v:[+m[3],+m[4],+m[5]],neg:neg});
    else if(m[6]!=null){const key=m[6].toLowerCase();let v=(m[7]!=null?m[7]:m[8]||'').trim().toLowerCase();
      // "origin: 1 2 3" (or "( 1 2 3 )"): the next two numbers belong to it
      if(key==='origin'){const vx=/^\s*\(?\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)?/.exec(v+q.slice(re.lastIndex));
        if(vx){re.lastIndex+=vx[0].length-v.length;T.push({k:'org',v:[+vx[1],+vx[2],+vx[3]],neg:neg});continue;}}
      T.push(v?{k:'kv',key:key,v:v,neg:neg}:{k:'has',key:key,neg:neg});}
    else{const w=m[9].toLowerCase();
      // "entity 25": the word entity followed by a number
      const nx=/^\s+(\d+)(?=\s|$)/.exec(q.slice(re.lastIndex));
      if((w==='entity'||w==='ent')&&nx){T.push({k:'kv',key:'entity',v:nx[1],neg:neg});re.lastIndex+=nx[0].length;continue;}
      if(w[0]==='$'&&w.length>1)T.push({k:'kv',key:'targetname',v:w.slice(1),neg:neg});
      else if(w!=='-')T.push({k:'word',v:w,neg:neg});}
  }
  return T;
}
function findGlob(pat){
  if(pat.indexOf('*')<0)return s=>s===pat;
  const r=new RegExp('^'+pat.split('*').map(x=>x.replace(/[.+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$');return s=>r.test(s);}
const FIND_ALIAS={class:'classname',cls:'classname',tn:'targetname',name:'targetname',tex:'texture',shader:'texture',ent:'entity'};
// does entity ei match term t?
function findEnt(ei,t){
  const e=MAP.ents[ei];
  if(t.k==='word')return searchText(ei).includes(t.v);
  if(t.k==='exact'){for(const kv of e.kv)if(String(kv[1]).toLowerCase()===t.v)return true;return false;}
  if(t.k==='has'){const key=FIND_ALIAS[t.key]||t.key;return e.kvl[key]!=null||e.kv.some(kv=>kv[0].toLowerCase()===key);}
  if(t.k==='org'){const o=ENTS[ei].origin;return !!o&&Math.abs(o[0]-t.v[0])<0.01&&Math.abs(o[1]-t.v[1])<0.01&&Math.abs(o[2]-t.v[2])<0.01;}
  const key=FIND_ALIAS[t.key]||t.key,ok=findGlob(t.v);
  if(key==='texture')return false;
  if(key==='entity')return ok(String(ei));
  if(key==='entnum'){const R=gameEnts()[ei];return !!R&&R.num>=0&&!R.gone&&ok(String(R.num));}
  if(key==='origin'){const v=parseVec(t.v,3),o=ENTS[ei].origin;return !!(v&&o)&&v.every((x,i)=>Math.abs(x-o[i])<0.01);}
  // the key as the game reads it ("$targetname" for targetname), else as written
  let val=e.kvl[key];if(val==null)for(const kv of e.kv)if(kv[0].toLowerCase()===key){val=kv[1];break;}
  return val!=null&&ok(String(val).toLowerCase());
}
// does texture ti (its name without textures/) match term t? Entity-only terms never do.
function findTex(nm,t){
  if(t.k==='word')return nm.includes(t.v);
  if(t.k==='exact')return nm===t.v||nm.split('/').pop()===t.v;
  if(t.k==='kv'&&(FIND_ALIAS[t.key]||t.key)==='texture'){const ok=findGlob(t.v);return ok(nm)||ok(nm.split('/').pop());}
  return false;
}
function runFind(q){
  q=q.trim();findRes=[];if(!q)return;
  const T=findTerms(q);if(!T.length)return;
  const pos=T.filter(t=>!t.neg),neg=T.filter(t=>t.neg);
  const texOnly=pos.length&&pos.every(t=>t.k==='kv'&&(FIND_ALIAS[t.key]||t.key)==='texture');
  if(!texOnly)for(let ei=0;ei<MAP.ents.length;ei++){
    if(pos.every(t=>findEnt(ei,t))&&!neg.some(t=>findEnt(ei,t)))findRes.push({e:ei});}
  // textures only when every term can say something of a texture
  if(pos.some(t=>t.k==='org'||t.k==='has'||(t.k==='kv'&&(FIND_ALIAS[t.key]||t.key)!=='texture')))return;
  for(const[ti,c]of texCounts()){const nm=TEX[ti].n.replace(/^textures\//,'').toLowerCase();
    if(pos.every(t=>findTex(nm,t))&&!neg.some(t=>findTex(nm,t)))findRes.push({t:ti,c:c});}
}
let _texCounts=null;
function texCounts(){if(_texCounts)return _texCounts;const m=new Map();for(let f=0;f<SC.nf;f++){const t=SC.faceTex[f];m.set(t,(m.get(t)||0)+1);}
  for(const R of MODELS)for(const s of R.surfs)m.set(s.ti,(m.get(s.ti)||0)+R.inst.length);
  _texCounts=[...m.entries()].sort((a,b)=>TEX[a[0]].n<TEX[b[0]].n?-1:1);return _texCounts;}
// What uses a texture: its brush faces, under the selection key each belongs to (a world
// brush, or the whole brush entity), and the entities whose model draws it on one surface or
// more (mi: [entity, how many of its model's surfaces], counted as texCounts counts them).
// Made once per texture.
let TEXUSE=null;
function texUse(ti){
  if(!TEXUSE)TEXUSE=new Map();
  let u=TEXUSE.get(ti);if(u)return u;
  const keys=new Map(),at=k=>{let o=keys.get(k);if(!o)keys.set(k,o={f:[],ei:-1});return o;},mi=[];
  for(const f of matFaces[ti]||[]){const ei=SC.faceEnt[f];at((ei>0&&!isWorldlike(ei))?'e'+ei:'p'+SC.facePrim[f]).f.push(f);}
  for(const R of MODELS){const n=R.surfs.reduce((s,x)=>s+(x.ti===ti?1:0),0);if(!n)continue;
    for(const ei of R.inst){at('e'+ei).ei=ei;mi.push([ei,n]);}}
  u={keys:keys,mi:mi};TEXUSE.set(ti,u);return u;}
// One of a texture's users is shown: its model, or one of its faces that has the texture.
function useShown(o){if(o.ei>=0&&entShown(o.ei))return true;for(const f of o.f)if(!faceVis||faceVis[f])return true;return false;}
// A texture row: its uses (faces and model surfaces), how many of them are hidden (Hide or a
// Show button), and whether everything shown that uses it is selected.
function texState(ti){
  const u=texUse(ti);let n=0,nh=0,any=false,sel=true;
  for(const f of matFaces[ti]||[]){n++;if(faceVis&&!faceVis[f])nh++;}
  for(const[ei,k]of u.mi){n+=k;if(!entShown(ei))nh+=k;}
  for(const[key,o]of u.keys){if(!useShown(o))continue;any=true;if(!SEL.has(key)){sel=false;break;}}
  return {n:n,nh:nh,sel:any&&sel};}
const openCls=new Set();
// the entities of each class, in map order (worldspawn first)
function classLists(){
  const cnt=new Map();for(let ei=0;ei<MAP.ents.length;ei++){const c=MAP.ents[ei].kvl.classname||'?';if(!cnt.has(c))cnt.set(c,[]);cnt.get(c).push(ei);}
  return cnt;
}
// Each tab's counts and hints go above the line (#listHead, in the Find section); the list
// goes under it, in a section of its own that is hidden while it has nothing to show.
function renderList(){
  const box=$('listBox');const head=[],rows=[];
  // hidden (by Hide or a Show button) in red; a class with only some of its entities
  // hidden in yellow
  const shown=ei=>ei===0||entVisible(ei);
  // the targetname first, then the class; the tooltip has all of it (the row cuts it short)
  const entRow=(ei,sub)=>{const e=MAP.ents[ei],X=ENTS[ei],sel=SEL.has('e'+ei)||(ei===0),hid=!shown(ei),tn=e.kvl.targetname,cls=e.kvl.classname||'?';
    const where=X.anchor?fvec(X.anchor):'';
    const tip=(tn?'$'+tn+'  ':'')+cls+'\nentity '+ei+(where?'\n'+where:'')+(hid?'\nhidden':'');
    return '<div class="li'+(sub?' sub':'')+(sel?' sel':'')+(hid?' hid':'')+'" data-e="'+ei+'" title="'+esc(tip)+'"><span class="sw" style="background:rgb('+X.col.map(v=>Math.round(v*255)).join(',')+')"'+
      (ei?' title="Shift+click: '+(hid?'show':'hide')+' this entity"':'')+'></span><span class="nm">'+
      esc(sub?(tn?'$'+tn:'entity '+ei):(tn?'$'+tn+'  ':'')+cls)+'</span><span class="ct">'+esc(where)+'</span></div>';};
  // the Entities tab: the targetname, else "entity" and its entity number; the number on the
  // right when the name doesn't give it. The tooltip has its class, numbers and origin.
  const numRow=(ei,R)=>{const e=MAP.ents[ei],X=ENTS[ei],tn=e.kvl.targetname,sel=SEL.has('e'+ei),hid=!shown(ei);
    const tip=(e.kvl.classname||'?')+(tn?' $'+tn:'')+'\nentity number '+R.num+', radnum '+R.rad+(X.anchor?'\n'+fvec(X.anchor):'')+(hid?'\nhidden':'');
    return '<div class="li'+(sel?' sel':'')+(hid?' hid':'')+'" data-e="'+ei+'" title="'+esc(tip)+'"><span class="sw" style="background:rgb('+X.col.map(v=>Math.round(v*255)).join(',')+')" title="Shift+click: '+(hid?'show':'hide')+' this entity"></span><span class="nm">'+
      esc(tn?'$'+tn:'entity '+R.num)+'</span><span class="ct">'+(tn?R.num:'')+'</span></div>';};
  if(curTab==='find'){
    runFind($('findIn').value);
    if(!$('findIn').value.trim())head.push('<div class="co">Type above to search every key and value (classname, targetname, target, model, spawnflags...) and every texture name. Enter selects everything found.</div>'+
      '<div class="co">· "exact value"</div>'+
      '<div class="co">· $targetname</div>'+
      '<div class="co">· key: value (classname:, texture:, #set:, entity:, entnum:, * in a value matches any text, e.g. classname: info_*)</div>'+
      '<div class="co">· key: (nothing after it) has that key at all</div>'+
      '<div class="co">· entity 25</div>'+
      '<div class="co">· ( x y z ) for an origin</div>'+
      '<div class="co">· -term leaves out what it matches</div>');
    else if(!findRes.length)head.push('<div class="co">Nothing matches.</div>');
    else{
      head.push('<div class="co">'+findRes.length+' found</div>');
      head.push('<div class="co">· Press Enter in search box to select all</div>');
      head.push('<div class="co">· Shift-click a colored square to hide it</div>');
      head.push('<div class="co">· Shift-click any green text to deselect it</div>');
    }
    let n=0;for(const r of findRes){if(++n>600){rows.push('<div class="co">... '+(findRes.length-600)+' more (Enter selects them all)</div>');break;}
      if(r.e!=null)rows.push(entRow(r.e,false));
      else rows.push(texRow(r.t));}
  }else if(curTab==='cls'){
    const cnt=classLists();
    const names=[...cnt.keys()].sort((a,b)=>a.toLowerCase()<b.toLowerCase()?-1:1);
    head.push('<div class="co">'+MAP.ents.length+' entities · '+names.length+' classes</div>');
    head.push('<div class="co">· click a class to list them & select all</div>');
    head.push('<div class="co">· shift-click a colored square to hide them</div>');
    head.push('<div class="co">· Shift-click any green text to deselect it</div>');
    for(const c of names){const l=cnt.get(c),open=openCls.has(c),X=ENTS[l[0]];
      const nh=l.reduce((s,ei)=>s+(shown(ei)?0:1),0), st=!nh?'':nh===l.length?' hid':' part';
      // green while every one of them that is shown is selected
      const ns=l.filter(ei=>ei>0&&shown(ei)), cs=ns.length>0&&ns.every(ei=>SEL.has('e'+ei));
      rows.push('<div class="li'+(cs?' sel':'')+st+'" data-c="'+esc(c)+'"'+(nh?' title="'+(nh===l.length?'all hidden':nh+' of '+l.length+' hidden')+'"':'')+'><span class="ar" data-o="'+esc(c)+'">'+(open?'▾':'▸')+'</span><span class="sw" style="background:rgb('+(X.ccol||X.col).map(v=>Math.round(v*255)).join(',')+')"'+
        (c!=='worldspawn'?' title="Shift+click: '+(nh===l.length?'show':'hide')+' every '+esc(c)+'"':'')+'></span><span class="nm">'+esc(c)+'</span><span class="ct">'+(nh?nh+' / ':'')+l.length+'</span></div>');
      if(open)for(const ei of l.slice(0,500))rows.push(entRow(ei,true));}
  }else if(curTab==='ent'){
    // the entities the game numbers, in their order (gameEnts: for the cvars' g_gametype,
    // skill, developer and sv_maxclients); not the world (1022), nor one that removes itself
    // as it spawns, whose number is left unused
    const G=gameEnts(),l=[];
    for(let ei=1;ei<MAP.ents.length;ei++){const R=G[ei];if(R.num>=0&&!R.gone)l.push(ei);}
    l.sort((a,b)=>G[a].num-G[b].num);
    const lo=l.length?G[l[0]].num:0,hi=l.length?G[l[l.length-1]].num:0;
    head.push('<div class="co" title="'+esc('The entities the game spawns with an entity number (as sv_showentnums shows them), for g_gametype '+CVARS.g_gametype+', skill '+CVARS.skill+
      (CVARS.developer?', developer 1':'')+' (the last group of the game cvars)'+(l.length?': numbers '+lo+' to '+hi:'')+'. The world is 1022 and the players come first (sv_maxclients '+CVARS.sv_maxclients+
      '). Simple entities (path nodes, player starts, waypoints...), lights and static props have no number; one that removes itself as it spawns (misc_model, func_remove) leaves its number unused.')+'">'+l.length+' real entities with entnums</div>');
    head.push('<div class="co">· click an entity to select it</div>');
    head.push('<div class="co">· shift-click a colored square to hide it</div>');
    head.push('<div class="co">· Shift-click any green text to deselect it</div>');
    // the client slots come first: entity 0 to sv_maxclients - 1, kept for the players
    const nc=Math.max(1,Math.min(+CVARS.sv_maxclients||1,lo||1e9));
    for(let k=0;k<nc;k++)rows.push('<div class="li res" data-r="'+k+'" title="'+esc(k?'reserved for $player['+(k+1)+'] in multiplayer':'reserved for $player, or $player[1] in multiplayer')+
      '"><span class="sw" style="background:var(--dim)"></span><span class="nm">entity '+k+'</span><span class="ct"></span></div>');
    for(const ei of l)rows.push(numRow(ei,G[ei]));
  }else{
    const used=texCounts();
    head.push('<div class="co">'+used.length+' textures</div>');
    head.push('<div class="co">· click one to select everything using it</div>');
    head.push('<div class="co">· shift-click a texture square to hide them</div>');
    head.push('<div class="co">· Shift-click any green text to deselect it</div>');
    for(const[ti]of used)rows.push(texRow(ti));
  }
  $('listHead').innerHTML=head.join('');
  box.innerHTML=rows.join('');
  $('listSect').style.display=rows.length?'':'none';
}
// A texture row: green while everything shown that uses it is selected; red when all of it is
// hidden, yellow when some (with the count hidden). Shift+click its square (.tsq) hides or
// shows everything using it.
function texRow(ti){
  const te=TEX[ti],u=TEXURL[ti],S=texState(ti),all=S.nh===S.n,st=!S.nh?'':all?' hid':' part';
  const tip=' title="Shift+click: '+(all?'show':'hide')+' every brush and entity using it"';
  const sq=u?'<img class="tsq" src="'+u+'" alt=""'+tip+'>'
    :'<span class="sw tsq" style="width:18px;height:18px;background:rgb('+(te.c||[.5,.5,.5]).map(v=>Math.round(v*255)).join(',')+')"'+tip+'></span>';
  const rt=te.n.replace(/^textures\//,'')+(te.f&TF_MISSING?' (missing)':'')+'\n'+S.n+' face'+(S.n===1?'':'s')+' and model surfaces use it'+(S.nh?'\n'+(all?'all hidden':S.nh+' of '+S.n+' hidden'):'');
  return '<div class="li'+(S.sel?' sel':'')+st+'" data-t="'+ti+'" title="'+esc(rt)+'">'+sq+
    '<span class="nm">'+esc(te.n.replace(/^textures\//,''))+(te.f&TF_MISSING?' <span style="color:var(--err)">(missing)</span>':'')+'</span><span class="ct">'+(S.nh?S.nh+' / ':'')+S.n+'</span></div>';}
// The second click of a double-click on a class or texture row. The first click rebuilds the
// list, so the row under the mouse is a new element by the second one, and the browser may
// neither fire dblclick nor count the click as a second one (e.detail): a click on the same
// row within the double-click time counts as well.
let lastRowClick=null;
function secondClick(e,key){
  const now=performance.now(),again=e.detail>1||(!!lastRowClick&&lastRowClick.key===key&&now-lastRowClick.t<500);
  lastRowClick=again?null:{key:key,t:now};
  return again;
}
$('listBox').addEventListener('click',e=>{
  const r=e.target.closest('.li');
  if(r&&r.classList.contains('res'))return;   // a client slot (Entities tab)
  // Shift+click a texture's square: hide everything that uses it (again: show it)
  if(e.shiftKey&&r&&r.hasAttribute('data-t')&&e.target.closest('.tsq')){toggleHideTex(+r.getAttribute('data-t'));return;}
  // Shift+click a row's coloured square: hide that entity, or every entity of the class
  // (again: show them)
  if(e.shiftKey&&r&&e.target.closest('.sw')&&(r.hasAttribute('data-e')||r.hasAttribute('data-c'))){
    if(r.hasAttribute('data-e'))toggleHideEnts([+r.getAttribute('data-e')],entName(+r.getAttribute('data-e')));
    else{const c=r.getAttribute('data-c');toggleHideEnts(classLists().get(c)||[],'every '+c);}
    return;}
  const o=e.target.closest('[data-o]');if(o){const c=o.getAttribute('data-o');if(openCls.has(c))openCls.delete(c);else openCls.add(c);renderList();return;}
  if(!r)return;
  // Shift+click a green (selected) row: deselect that entity, every entity of the class, or
  // everything that uses the texture; the rest of the selection stays
  if(e.shiftKey&&r.classList.contains('sel')&&!(r.hasAttribute('data-e')&&+r.getAttribute('data-e')===0)){deselectRow(r);return;}
  if(r.hasAttribute('data-e')){const ei=+r.getAttribute('data-e');if(!e.shiftKey)SEL.clear();if(ei)SEL.add('e'+ei);selectionChanged();if(ei&&!e.shiftKey)focusSelection();renderList();}
  // a class row selects the class and opens (or closes) its list of entities; a
  // double-click leaves it open and flies to the class
  else if(r.hasAttribute('data-c')){const c=r.getAttribute('data-c'),again=secondClick(e,'c:'+c);selectClass(c,e.shiftKey);
    if(again)openCls.add(c);else if(openCls.has(c))openCls.delete(c);else openCls.add(c);
    renderList();if(again)focusSelection();}
  else if(r.hasAttribute('data-t')){const ti=+r.getAttribute('data-t'),again=secondClick(e,'t:'+ti);
    selectByTexture(ti,e.shiftKey);selectionChanged();renderList();if(again)focusSelection();}
});
// Shift+click a selected (green) row in the right-side lists: take it out of the selection.
function deselectRow(r){
  let keys=[],nm;
  if(r.hasAttribute('data-e')){const ei=+r.getAttribute('data-e');keys=['e'+ei];nm=entName(ei);}
  else if(r.hasAttribute('data-c')){const c=r.getAttribute('data-c');keys=(classLists().get(c)||[]).filter(ei=>ei>0).map(ei=>'e'+ei);nm='every '+c;}
  else if(r.hasAttribute('data-t')){const ti=+r.getAttribute('data-t');keys=[...texUse(ti).keys.keys()];nm=TEX[ti]?TEX[ti].n.replace(/^textures\//,''):'?';}
  let n=0;for(const k of keys)if(SEL.delete(k))n++;
  selectionChanged();renderList();
  flash(nm+': '+n+' deselected, '+SEL.size+' still selected');
}
// Hide entities as Hide does (Ctrl+Z undoes it), or, when every one of them is hidden
// already, show again the ones Hide hid. Those a Show button hides stay hidden: the
// message names the button.
function toggleHideEnts(list,label){
  list=list.filter(ei=>ei>0);if(!list.length)return;
  const vis=list.filter(ei=>entVisible(ei));
  if(vis.length){
    const step={e:[],p:[]};
    for(const ei of vis)if(!hidEnt.has(ei)){hidEnt.add(ei);step.e.push(ei);SEL.delete('e'+ei);}
    if(step.e.length){HIDE_UNDO.push(step);if(HIDE_UNDO.length>500)HIDE_UNDO.shift();}
    rebuildWorld();selectionChanged();
    flash(label+': '+step.e.length+' hidden - Shift+click the square again to show '+(step.e.length===1?'it':'them')+', Ctrl+Z undoes');
    return;}
  const back=list.filter(ei=>hidEnt.has(ei));
  if(back.length){for(const ei of back)hidEnt.delete(ei);HIDE_UNDO.push({show:true,e:back,p:[]});if(HIDE_UNDO.length>500)HIDE_UNDO.shift();
    rebuildWorld();selectionChanged();}
  const still=list.filter(ei=>!entVisible(ei)), btn=filterNamesOf(still);
  flash(back.length?label+': '+back.length+' shown again'+(still.length?', '+still.length+' still hidden by '+btn:'')
    :label+': hidden by '+btn+', not by Hide');
}
// The Show buttons that hide these entities: by their kind, or (a brush entity) by its faces.
function filterNamesOf(list){
  let bits=0;const ents=new Set();
  for(const ei of list){bits|=ENTS[ei].cat&hiddenMask;if(ENTS[ei].hasGeo)ents.add(ei);}
  if(ents.size)for(let f=0;f<SC.nf;f++)if(ents.has(SC.faceEnt[f]))bits|=SC.faceCat[f]&hiddenMask;
  return filterNamesFor(bits);
}
// ...and those that hide what uses a texture: its faces' kinds and its models' entities'
function texFilterNames(ti){
  let bits=0;for(const f of matFaces[ti]||[])bits|=SC.faceCat[f]&hiddenMask;
  for(const[ei]of texUse(ti).mi)bits|=ENTS[ei].cat&hiddenMask;
  return filterNamesFor(bits);
}
function filterNamesFor(bits){
  // the buttons that are off: Entities only when all of it is (not just its Lights, say)
  let names=FILTERS.filter(f=>(f.m&bits)&&(hiddenMask&f.m)===f.m).map(f=>f.l);
  if(!names.length)names=FILTERS.filter(f=>f.m&bits).map(f=>f.l);
  return names.length?'the '+names.join(' / ')+' button'+(names.length>1?'s':''):'a Show button';
}
// Shift+click a texture's square: hide everything shown that uses it (each world brush, brush
// entity and model entity, as Hide does: Ctrl+Z undoes it), or, when all of it is hidden
// already, show again what Hide hid. What a Show button hides stays hidden: the message
// names the button.
function toggleHideTex(ti){
  const u=texUse(ti),nm=TEX[ti]?TEX[ti].n.replace(/^textures\//,''):'?';
  const vis=[...u.keys].filter(([,o])=>useShown(o)).map(([k])=>k);
  if(vis.length){
    const step={e:[],p:[]};
    for(const k of vis){const i=+k.slice(1);
      if(k[0]==='e'){if(!hidEnt.has(i)){hidEnt.add(i);step.e.push(i);}}else if(!hidPrim.has(i)){hidPrim.add(i);step.p.push(i);}
      SEL.delete(k);}
    if(step.e.length||step.p.length){HIDE_UNDO.push(step);if(HIDE_UNDO.length>500)HIDE_UNDO.shift();}
    rebuildWorld();selectionChanged();
    const n=step.e.length+step.p.length;
    flash(nm+': '+n+' hidden - Shift+click the square again to show '+(n===1?'it':'them')+', Ctrl+Z undoes');
    return;}
  const back={e:[],p:[]};
  for(const k of u.keys.keys()){const i=+k.slice(1);
    if(k[0]==='e'){if(hidEnt.has(i)){hidEnt.delete(i);back.e.push(i);}}else if(hidPrim.has(i)){hidPrim.delete(i);back.p.push(i);}}
  const nb=back.e.length+back.p.length;
  if(nb){HIDE_UNDO.push({show:true,e:back.e,p:back.p});if(HIDE_UNDO.length>500)HIDE_UNDO.shift();rebuildWorld();selectionChanged();}
  const still=[...u.keys.values()].filter(o=>!useShown(o)).length;
  flash(nb?nm+': '+nb+' shown again'+(still?', '+still+' still hidden by '+texFilterNames(ti):'')
    :nm+': hidden by '+texFilterNames(ti)+', not by Hide');
}
function selectFindResults(){runFind($('findIn').value);SEL.clear();
  for(const r of findRes){if(r.e!=null&&r.e>0)SEL.add('e'+r.e);else if(r.t!=null)selectByTexture(r.t,true);}
  selectionChanged();flash(SEL.size+' selected');}

// ============================================================================
//  The "more info" card (N or Ctrl+click; Ctrl+Shift+click or middle-click: a face's texture)
// ============================================================================
let infoMode='sel';
function hideInfo(){$('info').classList.remove('on');}
const CF_NAMES=[[1,'solid'],[2,'ladder'],[8,'lava'],[0x10,'slime'],[0x20,'water'],[0x40,'fog'],[0x2000,'fence'],[0x8000,'areaportal'],
 [0x10000,'playerclip'],[0x20000,'monsterclip'],[0x40000,'weaponclip'],[0x80000,'vehicleclip'],[0x100000,'shootonly'],[0x1000000,'origin'],
 [0x8000000,'detail'],[0x10000000,'structural'],[0x20000000,'translucent'],[0x40000000,'trigger'],[0x80000000,'nodrop']];
const SF_NAMES=[[1,'nodamage'],[2,'slick'],[4,'sky'],[8,'ladder'],[0x10,'noimpact'],[0x20,'nomarks'],[0x40,'castshadow'],[0x80,'nodraw'],
 [0x100,'nolightmap'],[0x200,'alphashadow'],[0x400,'nosteps'],[0x800,'nonsolid'],[0x1000,'overbright'],[0x2000,'paper'],[0x4000,'wood'],
 [0x8000,'metal'],[0x10000,'rock'],[0x20000,'dirt'],[0x40000,'grill'],[0x80000,'grass'],[0x100000,'mud'],[0x200000,'puddle'],[0x400000,'glass'],
 [0x800000,'gravel'],[0x1000000,'sand'],[0x2000000,'foliage'],[0x4000000,'snow'],[0x8000000,'carpet'],[0x10000000,'backside'],
 [0x20000000,'nodlight'],[0x40000000,'hint'],[0x80000000,'patch']];
function bitNames(v,tab){v=v>>>0;const out=[];for(const[b,nm]of tab)if(v&(b>>>0))out.push(nm);return out;}
// A path node's label tag: its highest spawnflag by name, "[CORNER_RIGHT]" for COVER +
// CORNER_RIGHT (the more particular kind; one name keeps the label short), else "".
// The outline's colour (nodeOutline) goes by the first of its own order instead.
function nodeFlagTag(e){
  if(e.cls!=='info_pathnode')return '';
  const v=parseInt(e.kvl.spawnflags||'0',10)>>>0;if(!v)return '';
  const d=(D.defs||{})[e.cls],names=d&&d.f?d.f:[];
  for(let b=Math.min(31,names.length-1);b>=0;b--)
    if((v>>>b)&1){const nm=names[b];if(nm&&nm.toLowerCase()!=='x')return ' ['+nm+']';}
  return '';
}
function spawnflagNames(ei){const e=MAP.ents[ei];return sfNamesOf(e.cls,e.kvl.spawnflags);}
// a spawnflags value as its bits, each with the class's name for it: "8 CONCEALMENT, 2 DUCK"
function sfNamesOf(cls,val){
  const v=parseInt(val||'0',10)>>>0;if(!v)return '';
  const d=(D.defs||{})[cls], names=d&&d.f?d.f:[], ed=D.editorFlags||{}, out=[];
  for(let b=0;b<32;b++)if(v&(1<<b)>>>0){let nm=(b<names.length&&names[b].toLowerCase()!=='x')?names[b]:(ed[b]||'');out.push(((1<<b)>>>0)+(nm?' '+nm:''));}
  return out.join(', ');
}
// What Modify has changed on one of the map's entities and not saved yet, for its info card:
// each key whose value differs, the map's value struck through and the new one after it
// (spawnflags with their names), or that it is deleted. The rest of the card is the map's own.
function modChangesHtml(ei){
  const m=MOD&&MOD.ents?MOD.ents.find(x=>x.ei===ei):null;
  if(!m||!(m.del||modKvEdited(m)))return '';
  let h='<h4>Changed in Modify (not saved yet)<span class="sp"></span>'+(m.del?'':copyBtn(modText(m),'Copy'))+'</h4>';
  if(m.del)return h+'<div class="warn">DEL: deleted in Modify, so Save as .bsp / .map leaves it out. Restore (or Undo, Alt+Z) puts it back.</div>';
  const first=kv=>{const M=new Map();for(const[k,v]of kv){const l=k.toLowerCase();if(!M.has(l))M.set(l,[k,v]);}return M;};
  const old=first(m.orig||[]),nw=first(m.kv),cls=modCls(m)||MAP.ents[ei].cls,rows=[];
  const show=(l,v)=>v==null?'(none)':esc(v)+(l==='spawnflags'?' ['+esc(sfNamesOf(cls,v)||'none')+']':'');
  for(const l of new Set([...old.keys(),...nw.keys()])){
    const a=old.get(l),b=nw.get(l),av=a?a[1]:null,bv=b?b[1]:null;if(av===bv)continue;
    rows.push([(b||a)[0],'<span class="co" style="text-decoration:line-through">'+show(l,av)+'</span> → <span style="color:var(--warn)">'+show(l,bv)+'</span>']);}
  h+=rows.length?kvTable(rows):'<div class="note">Only the order of its keys changed.</div>';
  return h+'<div class="note">The sections below show the map\'s own keys, as it was loaded.</div>';
}
function srcText(a,b){return D.srcText.slice(a,b);}
function card(title,body){$('infoScr').style.display=(infoMode==='scr'&&D.scr&&D.scr.files&&D.scr.files.length)?'':'none';$('infoTitle').textContent=title;$('infoBody').innerHTML=body;$('info').classList.add('on');$('infoBody').scrollTop=0;}
function kvTable(rows){return '<table>'+rows.map(r=>'<tr><td class="k">'+esc(r[0])+'</td><td>'+r[1]+'</td></tr>').join('')+'</table>';}
function copyBtn(text,label){return ' <button class="sm" data-copy="'+esc(text)+'">'+(label||'Copy')+'</button>';}
// Open (beside Copy on a card's .map source): in the launcher's pane, the launcher opens the
// .map in the Text Editor at this block's line (where the editor takes a line: Notepad++,
// VS Code, Sublime Text...); in a browser, the whole .map opens as text in a new tab.
function openBtn(off){return ' <button class="sm" data-openmap="'+off+'" title="Open the .map: in the launcher, in your Text Editor at this line; in a browser, as text in a new tab">Open</button>';}
let LINE_STARTS=null;
function lineOf(off){                    // the 1-based line of a text offset in the .map
  if(!LINE_STARTS){const s=D.srcText,a=[0];let i=-1;while((i=s.indexOf('\n',i+1))>=0)a.push(i+1);LINE_STARTS=Int32Array.from(a);}
  let lo=0,hi=LINE_STARTS.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(LINE_STARTS[m]<=off)lo=m;else hi=m-1;}
  return lo+1;
}
function openMapAt(off){
  const line=lineOf(off);
  try{if(window.chrome&&window.chrome.webview){
    window.chrome.webview.postMessage('mohaa-open-map\n'+line+'\n'+((D.bsp&&D.bsp.mapFile)||''));
    flash('Opening the .map in your Text Editor (line '+line+')');return;}}catch(_e){}
  window.open(URL.createObjectURL(new Blob([D.srcText],{type:'text/plain;charset=utf-8'})),'_blank');
  flash('The .map opened as text in a new tab (this block starts on line '+line+')');
}
// ---- blocks of the .map the reader skipped (readMap's errors) ----------------------
// Each is listed with its entity and primitive, its line in the .map and why it was
// skipped; the rest of the map is drawn without it. The red line under the map's stats
// opens the list, and in the launcher's pane it goes to the Output console too.
function errorLines(){                 // [{line, text}] for MAP.errors, in one pass over the text
  if(MAP.errLines)return MAP.errLines;
  const s=D.srcText, out=new Array(MAP.errors.length);
  const order=MAP.errors.map((x,i)=>i).sort((a,b)=>MAP.errors[a].off-MAP.errors[b].off);
  let line=1,pos=0;
  for(const i of order){
    const off=MAP.errors[i].off;let j;
    while((j=s.indexOf('\n',pos))>=0&&j<off){line++;pos=j+1;}
    let e=s.indexOf('\n',pos);if(e<0)e=s.length;
    const tx=s.slice(pos,e).trim();
    out[i]={line:line,text:tx.length>160?tx.slice(0,160)+'…':tx};
  }
  return MAP.errLines=out;
}
// How many of the map's entities the game makes real entities (each with an entity
// number; the game has 1024 slots), how many it keeps as simple ones without a number
// (path nodes, player starts, waypoints..., and the lights and info_nulls it drops once the
// map is loaded), and how many are static props. The class lists come from the build
// (SIMPLE_CLASSES / DROPPED_CLASSES in mohaa_entdefs.py).
function entityKinds(){
  const ek=D.ek||{}, simple=new Set([...(ek.simple||[]),...(ek.dropped||[])]);
  let real=0,smp=0,stat=0,scr=0,nodes=0;
  MAP.ents.forEach((e,ei)=>{
    if(e.cls==='info_pathnode')nodes++;
    if(e.scr){if(!simple.has(e.cls)&&!e.cls.startsWith('static_'))scr++;return;}
    if(isStaticProp(ei))stat++;else if(simple.has(e.cls))smp++;else real++;});
  return {real:real,simple:smp,stat:stat,scr:scr,nodes:nodes};
}
// ---- the game's hard limits -------------------------------------------------------------
// maxentities 1024 (gamecvars.cpp); Level::AllocEdict keeps the last two (ENTITYNUM_WORLD,
// ENTITYNUM_NONE) and starts after the client slots (game.maxclients: 1 in single player,
// sv_maxclients in multiplayer), and stops the map with "no free edicts" past that.
// MAX_PATHNODES 4096 (navigate.h): PathSearch::AddNode stops it with "Exceeded MAX_PATHNODES!".
const ENT_MAX=1022, MAX_PATHNODES=4096;
function mapIsMP(){return /(^|[\\/])maps[\\/](dm|obj|mp)[\\/]/i.test((D.path||'')+' '+(D.srcFile||''))||/^(dm|obj|mp)_|^mohdm/i.test(D.name||'');}
function entLimitText(K){
  const mp=mapIsMP(),used=K.real+K.scr;
  return 'MOHAA has 1024 entity slots (maxentities). The world and "none" keep two, and the first ones are kept for the players: 1 in single player, sv_maxclients in multiplayer (often 16 to 32). Past the last free one the map stops: "Level::AllocEdict: no free edicts". Whatever is spawned while playing (weapons, projectiles, effects, the players\' items) takes slots too, so keep well below.\n\nThis map: '+K.real+' real'+(K.scr?' + '+K.scr+' the level script spawns':'')+' = '+used+' of '+(ENT_MAX-1)+' with one player'+(mp?', '+(ENT_MAX-32)+' with 32':'')+'.';
}
function nodeLimitText(K){
  return 'Path nodes (info_pathnode, every kind: cover, sniper, crouch...): at most 4096 (MAX_PATHNODES); one more stops the map with "Exceeded MAX_PATHNODES!". The other simple entities have no fixed limit in the game.\n\nThis map: '+K.nodes+' path node'+(K.nodes===1?'':'s')+' of 4096.';
}
// a class as the game takes it: 'node', 'simple' (no entity number), 'static' or 'real'
function modKindOf(cls){
  const ek=D.ek||{};if(!modKindOf.S)modKindOf.S=new Set([...(ek.simple||[]),...(ek.dropped||[])]);
  if(cls==='info_pathnode')return 'node';if(/^static_/.test(cls))return 'static';
  return modKindOf.S.has(cls)?'simple':'real';
}
// the map's counts with Modify's new entities (and changed classes) in
function modLimits(extra){
  const K=entityKinds();let real=K.real+K.scr,nodes=K.nodes;
  for(const m of MOD.ents){const k=modKindOf(modCls(m)||'');
    if(modIsMap(m)){const k0=modKindOf(MAP.ents[m.ei].cls);if(k0===k)continue;   // a classname changed
      if(k0==='real')real--;if(k0==='node')nodes--;}
    if(k==='real')real++;if(k==='node')nodes++;}
  if(extra==='real')real++;if(extra==='node')nodes++;
  const mp=mapIsMP(),rmax=ENT_MAX-1;            // with one player; in multiplayer more go
  return {real:real,nodes:nodes,rmax:rmax,mp:mp};
}
// a new one of this class: refused past the limit, a warning near it
function modLimitCheck(cls){
  const k=modKindOf(cls);if(k!=='real'&&k!=='node')return true;
  const L=modLimits(k);
  if(k==='node'&&L.nodes>MAX_PATHNODES){flash('No more path nodes: the map would have '+L.nodes+', and the game takes at most 4096 (MAX_PATHNODES); it stops the map with "Exceeded MAX_PATHNODES!"');return false;}
  if(k==='real'&&L.real>L.rmax){flash('No more real entities: the map would have '+L.real+' (with what its level script spawns); the game has '+L.rmax+' slots for them with one player and stops the map with "no free edicts"');return false;}
  if(k==='node'&&L.nodes>MAX_PATHNODES-200)flash('Path nodes: '+L.nodes+' of 4096 (MAX_PATHNODES)');
  if(k==='real'&&L.real>(L.mp?L.rmax-32-64:L.rmax-64))flash('Real entities: '+L.real+' of '+L.rmax+(L.mp?' ('+(L.rmax-31)+' with 32 players)':'')+'; what is spawned while playing takes slots too');
  return true;
}
// A static prop: in a .map, a static_* class (the compiler makes those into static models);
// decompiled from a .bsp, every entity from the static model lump, written after the
// others (some take a .tik class name without the prefix).
function isStaticProp(ei){const fs=D.bsp&&D.bsp.firstStatic;
  if(MAP.ents[ei].scr)return false;
  return (fs>0)?ei>=fs:MAP.ents[ei].cls.startsWith('static_');}
function errText(x,l){
  return 'entity '+x.ent+' ('+(MAP.ents[x.ent]?entName(x.ent):'?')+')'+(x.prim>=0?', '+x.kind+' '+x.prim:'')+', line '+l.line+': '+x.msg;
}
function infoErrors(){
  const L=errorLines(), n=MAP.errors.length, shown=Math.min(n,300);
  let h='<div class="note">The .map reader skipped '+(n===1?'this block':'these '+n+' blocks')+' and drew the rest of the map without '+(n===1?'it':'them')+
    '. Line numbers are in '+(D.kind==='bsp'?'the .map decompiled from the .bsp (written next to this page; the launcher\'s .map button opens it)':'the .map')+'.</div>';
  for(let i=0;i<shown;i++){const x=MAP.errors[i],l=L[i],e=MAP.ents[x.ent];
    // the entity links to it (select, fly to, its card); the world isn't one thing to fly to
    const who=!e?'entity '+x.ent:(x.ent>0&&!isWorldlike(x.ent))?linkEnt(x.ent):esc(entName(x.ent))+' <span class="co">(entity '+x.ent+')</span>';
    h+='<h4>'+(x.prim>=0?esc(x.kind)+' '+x.prim+' of ':'')+'entity '+x.ent+'<span class="sp"></span>line '+l.line+'</h4>'+
      '<div>'+who+'</div><div class="warn">'+esc(x.msg)+'</div><pre>'+esc(l.text)+'</pre>';}
  if(n>shown)h+='<div class="note">… and '+(n-shown)+' more.</div>';
  card(n+' unreadable block'+(n===1?'':'s')+' skipped',h);
}
function reportMapErrors(){
  const n=MAP.errors.length;
  if(!n)return;
  console.warn('map blocks skipped',MAP.errors);
  try{if(window.chrome&&window.chrome.webview){const L=errorLines();
    window.chrome.webview.postMessage('mohaa-map-errors\n'+TITLE+'\n'+n+'\n'+MAP.errors.slice(0,100).map((x,i)=>errText(x,L[i])).join('\n'));}}catch(_e){}
}
$('stats').addEventListener('click',e=>{if(e.target.closest('[data-errs]'))showInfo('errs');if(e.target.closest('[data-scr]'))scrCard();
  if(e.target.closest('[data-leak]')){if(!view.leak)toggleDisplay('leak');else leakCard();}});
function showInfo(mode){
  infoMode=mode||'sel';
  if(infoMode==='errs')return infoErrors();
  if(infoMode==='leak')return leakCard();
  if(infoMode==='scr')return scrCard();
  if(infoMode==='face'){if(lastHit&&lastHit.face>=0)return infoFace(lastHit);}
  // a new entity of Modify's selected: its own card (it isn't in the .bsp yet)
  if(infoMode==='sel'&&MOD.ents[MOD.sel]&&!modIsMap(MOD.ents[MOD.sel]))return infoMod(MOD.sel);
  if(!SEL.size){if(lastHit&&lastHit.face>=0&&infoMode!=='sel')return infoFace(lastHit);card('Nothing selected','<div class="note">Click a brush or entity first (Ctrl+click opens this card straight away).</div>');return;}
  const ents=[...selectedEnts()], prims=selectedPrims();
  if(SEL.size===1&&ents.length===1)return infoEntity(ents[0]);
  if(SEL.size===1&&prims.length===1)return infoPrim(prims[0]);
  return infoMulti(ents,prims);
}
// ---- the card of a new entity (Modify) ----------------------------------------------------
// As a map entity's card, but for what isn't in the .bsp yet: no entity number, the node
// number it will take, its links as worked out here, and its parameters to edit in place
// (applied as typed, when they read).
let _cardModT=0;
function infoMod(i){
  const m=MOD.ents[i];if(!m)return;
  let h='<div id="cardModDyn">'+infoModDyn(i)+'</div>';
  const busy=MOD.edit===i;
  h+='<h4>Parameters<span class="sp"></span>'+copyBtn(modText(m),'Copy')+'</h4>';
  h+='<textarea id="cardModTxt" spellcheck="false" style="width:100%;box-sizing:border-box;min-height:150px;resize:vertical;font:12px/1.4 Consolas,Menlo,monospace;background:var(--bg);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:6px 8px"'+(busy?' disabled':'')+'>'+esc(modText(m))+'</textarea>';
  h+='<div class="note" id="cardModErr">'+(busy?'Being edited in the Edit parameters box: close it to edit here.':'"key" "value" lines, applied as you type; its AI routes follow.')+'</div>';
  card(modName(m)+' (new)',h);
  const ta=$('cardModTxt');
  ta.addEventListener('input',()=>{clearTimeout(_cardModT);_cardModT=setTimeout(()=>{
    const mm=MOD.ents.indexOf(m);if(mm<0)return;
    try{m.kv=modParse(ta.value);$('cardModErr').textContent='"key" "value" lines, applied as you type; its AI routes follow.';$('cardModErr').classList.remove('warn');
      modChanged(true);$('infoTitle').textContent=modName(m)+' (new)';const dyn=$('cardModDyn');if(dyn)dyn.innerHTML=infoModDyn(mm);}
    catch(err){$('cardModErr').textContent=err.message;$('cardModErr').classList.add('warn');}},250);});
  ta.addEventListener('keydown',e=>{if(e.key==='Escape'){ta.blur();e.preventDefault();e.stopPropagation();}});
}
function infoModDyn(i){
  const m=MOD.ents[i],o=modOrigin(m),b=modBox(m),X=modLook(m),c=X.mcol||X.col,cls=modCls(m),tn=modKv(m,'targetname');
  let h='<div><span class="sw" style="background:rgb('+c.map(v=>Math.round(v*255)).join(',')+')"></span><b>'+esc(modKv(m,'classname')||'?')+'</b>'+(tn?'  <span style="color:var(--accent)">$'+esc(tn)+'</span>':'')+' <span class="warn">new</span></div>';
  h+='<div class="note">Added in Modify, not saved: it isn\'t in the .bsp or the .map yet, so it has no entity number (the game gives one when the saved map loads) and the level script, Find and the cvars don\'t see it. Save as .bsp / .map writes it after the map\'s own entities.</div>';
  const amin=[o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]],amax=[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]];
  const rows=[['origin',esc(fvec(o))+copyBtn(fvec(o))],['box',esc(fvec(b.mins)+' '+fvec(b.maxs))],['absmin',esc(fvec(amin))],['absmax',esc(fvec(amax))]];
  const sf=parseInt(modKv(m,'spawnflags')||'0',10)>>>0;
  if(sf){const d=(D.defs||{})[cls],names=d&&d.f?d.f:[],ed=D.editorFlags||{},out=[];
    for(let k=0;k<32;k++)if(sf&(1<<k)>>>0){const nm=(k<names.length&&names[k].toLowerCase()!=='x')?names[k]:(ed[k]||'');out.push(((1<<k)>>>0)+(nm?' '+nm:''));}
    rows.push(['spawnflags',esc(out.join(', '))]);}
  h+='<h4>Origin and box</h4>'+kvTable(rows);
  if(cls==='info_pathnode'){
    h+='<h4>AI paths (ai_showroutes)</h4>';
    const A=PA(),k=A&&A.mod?A.mod.indexOf(m):-1;
    if(!A)h+='<div class="note">The paths are still being worked out.</div>';
    else if(k<0)h+='<div class="note">'+(modBusy(i)?'Being edited: it joins the paths when you are done.':'Not in the paths.')+'</div>';
    else{const n=A.n0+k,pn=pnEnts(),fh=CVARS.ai_fallheight,C=A.c,out=new Map(),inn=new Map();
      for(let q=0;q<C.length;q+=9){const a=C[q]|0,bb=C[q+1]|0,f=C[q+2];if(a===n)out.set(bb,f);if(bb===n)inn.set(a,f);}
      const nm=j=>j<A.n0?(pn[j]!=null?linkEnt(pn[j]):'node '+j):'<b>new node '+(j-A.n0+1)+'</b>';
      const lst=a=>a.slice(0,60).map(([j,f])=>nm(j)+(f?' <span class="co">drop '+f+(f>fh?', past ai_fallheight':'')+'</span>':'')).join(', ');
      const two=[],to=[],from=[];
      for(const[j,f]of out){if(inn.has(j))two.push([j,f]);else to.push([j,f]);}
      for(const[j,f]of inn)if(!out.has(j))from.push([j,f]);
      h+='<div class="note">node '+n+' (after the map\'s '+A.n0+'), as the saved map will number it; dropped to the floor at '+esc(fvec([A.o[n*3],A.o[n*3+1],A.o[n*3+2]]))+((A.f[n]&1)?' · DONT_LINK: never connected':'')+'</div>';
      if(!out.size&&!inn.size)h+='<div>no paths'+((A.f[n]&1)?'':' (ai_showroutes draws a red X here)')+'</div>';
      if(two.length)h+='<div>both ways ('+two.length+'): '+lst(two)+'</div>';
      if(to.length)h+='<div>one way to ('+to.length+'): '+lst(to)+'</div>';
      if(from.length)h+='<div>one way from ('+from.length+'): '+lst(from)+'</div>';
      for(const x of paIssueList(n))h+='<div class="'+(x.lv===0?'note':'warn')+'">'+esc(x.t)+'</div>';
      h+='<div class="note">Links are at most 384 units across the ground, 48 a node and 128 nodes a 256-unit cell; a drop deeper than ai_fallheight ('+fh+', or the actor\'s own fallheight) isn\'t taken, shallower ones one way only.</div>';}
  }
  const d=(D.defs||{})[cls];
  if(d&&d.d)h+='<h4>Class</h4><div class="desc">'+esc(d.d)+'</div>';
  return h;
}
function linkEnt(ei){return '<a data-sel="'+ei+'">'+esc(entName(ei))+'</a> <span class="co">(entity '+ei+')</span>';}
function infoEntity(ei){
  const e=MAP.ents[ei],X=ENTS[ei],cls=e.kvl.classname||'?',tn=e.kvl.targetname,b=X.box,def=X.def;
  let h='';
  h+='<div><span class="sw" style="background:rgb('+X.col.map(v=>Math.round(v*255)).join(',')+')"></span><b>'+esc(cls)+'</b>'+(tn?'  <span style="color:var(--accent)">$'+esc(tn)+'</span>':'')+'</div>';
  h+='<div class="note">'+(e.scr?'spawned by the level script ('+esc(scrWhere(e.scr.f,e.scr.l))+'), not in the .map':'entity '+ei+' in the .map')+(e.prims.length?' · '+e.prims.filter(p=>p&&p.kind===0).length+' brush(es)'+(e.patches.length?', '+e.patches.length+' patch(es)':'')+(e.terrains.length?', '+e.terrains.length+' terrain block(s)':''):'')+
     (X.model>=0?' · model '+esc(D.models[X.model].p):'')+'</div>';
  // the number the game gives it (sv_showentnums, script errors), for the game the list's cvars set
  if(ei>0){const R=gameEnts()[ei];
    h+='<div class="note">in game: '+(R.num>=0?'entity number '+R.num+', radnum '+R.rad+(R.gone?' ('+esc(R.why)+')':''):esc(R.why||'no entity number'))+
      ' <span class="co">(g_gametype '+CVARS.g_gametype+', skill '+CVARS.skill+(CVARS.developer?', developer 1':'')+')</span></div>';}
  h+=modChangesHtml(ei);                      // Modify's unsaved changes to it, if any
  if(b){
    const o=b.origin, amin=[o[0]+b.wmins[0],o[1]+b.wmins[1],o[2]+b.wmins[2]], amax=[o[0]+b.wmaxs[0],o[1]+b.wmaxs[1],o[2]+b.wmaxs[2]];
    const ss='setsize '+fvec(b.mins)+' '+fvec(b.maxs);
    h+='<h4>Origin and setsize<span class="sp"></span>'+copyBtn(fvec(o)+'\n'+ss,'Copy')+'</h4>';
    h+=kvTable([['origin',esc(fvec(o))+copyBtn(fvec(o))],['setsize',esc(fvec(b.mins)+' '+fvec(b.maxs))+copyBtn(ss)],
      ['size',esc(fvec([b.maxs[0]-b.mins[0],b.maxs[1]-b.mins[1],b.maxs[2]-b.mins[2]]))],
      ['absmin',esc(fvec(amin))],['absmax',esc(fvec(amax))]]);
    h+='<div class="note'+(b.exact?'':' warn')+'">'+(b.exact?'From: ':'Approximate - from: ')+esc(b.how)+'</div>';
    if(!b.exact&&X.hasGeo)h+='<div class="note">MOHAA keeps no readable setsize for brush entities, so this is the box around its brushes measured from where the compiler puts its origin. Open the .bsp instead of the .map for the exact box.</div>';
    // script lines
    const name=tn?'$'+tn:'local.ent';
    // a door's "angle" is the way it opens (Door::SetDir), not a turn of the door
    const ang=(e.kvl.angles||(e.kvl.angle&&!DOOR_CLASSES[cls]))?fvec(entAngles(e.kvl)):null;
    let sc='';
    if(cls.startsWith('trigger_')){
      sc='local.trig = spawn '+cls+(tn?' "targetname" "'+tn+'"':'')+'\nlocal.trig.origin = '+fvec(o)+'\nlocal.trig setsize '+fvec(b.mins)+' '+fvec(b.maxs);
      if(e.kvl.spawnflags)sc+='\nlocal.trig.spawnflags = '+e.kvl.spawnflags;
      if(e.kvl.setthread)sc+='\nlocal.trig setthread '+e.kvl.setthread;
      if(e.kvl.target)sc+='\nlocal.trig.target = "'+e.kvl.target+'"';
    }else{
      sc=name+'.origin = '+fvec(o)+(ang?'\n'+name+'.angles = '+ang:'')+'\n'+name+' setsize '+fvec(b.mins)+' '+fvec(b.maxs);
    }
    h+='<h4>Script<span class="sp"></span>'+copyBtn(sc)+'</h4><pre>'+esc(sc)+'</pre>';
  }
  // keys
  h+='<h4>Keys<span class="sp"></span>'+copyBtn(e.kv.map(kv=>'"'+kv[0]+'" "'+kv[1]+'"').join('\n'),'Copy')+'</h4>';
  h+=kvTable(e.kv.map(kv=>[kv[0],esc(kv[1])]));
  const sf=spawnflagNames(ei);if(sf)h+='<div class="note">spawnflags: '+esc(sf)+'</div>';
  if(X.marker===1&&X.mk!=null)h+=radiantNote(X,e);
  // targets
  const tg=e.kvl.target;
  const tos=tg?(ENTS.tn.get(tg)||[]):[];
  const froms=tn?MAP.ents.map((x,i)=>i).filter(i=>MAP.ents[i].kvl.target===tn):[];
  if(tg||froms.length){
    h+='<h4>Links</h4>';
    if(tg)h+='<div>target <b>'+esc(tg)+'</b> → '+(tos.length?tos.map(linkEnt).join(', '):'<span class="warn">no entity has this targetname</span>')+'</div>';
    if(froms.length)h+='<div>targeted by: '+froms.map(linkEnt).join(', ')+'</div>';
    h+='<div class="note"><a data-path="'+ei+'">Select the whole path</a> (Ctrl+Alt+click): everything it leads to and everything that leads to it.</div>';
  }
  if(e.cls==='info_pathnode')h+=pathNodeInfo(ei);
  h+=doorInfo(ei);
  h+=expInfo(ei);
  // textures of a brush entity
  if(X.hasGeo){const cnt=new Map();for(const pi of primsOfEnt(ei)){const p=SC.prims[pi];for(let f=p.f0;f<p.f1;f++){const t=SC.faceTex[f];cnt.set(t,(cnt.get(t)||0)+1);}}
    if(cnt.size){h+='<h4>Textures</h4>'+kvTable([...cnt.entries()].map(([t,c])=>[c+'x','<a data-tex="'+t+'">'+esc(TEX[t].n.replace(/^textures\//,''))+'</a>']));}}
  if(lastHit&&lastHit.ent===ei&&lastHit.face>=0)h+=faceHtml(lastHit.face,true);
  if(def&&def.d)h+='<h4>About '+esc(def.n)+'</h4><div class="desc">'+esc(def.d)+'</div>'+(def.s?'<div class="note">from '+esc(def.s)+'</div>':'');
  if(e.scr)h+=scrEntHtml(e);
  else if(e.scrMods){const L=e.scrMods.map(m=>'// '+scrWhere(m[3],m[4])+'\n'+m[5]).join('\n');
    h+='<h4>Changed by the level script<span class="sp"></span>'+copyBtn(L,'Copy')+'</h4><pre>'+esc(L)+'</pre>'+
      '<div class="note">Its "target" as the script sets it while the game runs (the .map below has its own).</div>';}
  if(!e.scr)h+='<h4>.map source<span class="sp"></span>'+copyBtn(srcText(e.ts,e.te),'Copy')+openBtn(e.ts)+'</h4><pre>'+esc(clipText(srcText(e.ts,e.te)))+'</pre>';
  card(entName(ei),h);
}
// A path node's paths in the map's .pth (what ai_showroutes draws): node i is the map's
// i-th info_pathnode.
let PN_ENTS=null;
function pathNodeInfo(ei){
  if(!pathsOk()&&!PA_GEN)return '';
  if(!PN_ENTS){PN_ENTS=[];MAP.ents.forEach((e,i)=>{if(e.cls==='info_pathnode'&&!e.scr)PN_ENTS.push(i);});}
  const P=PA();if(!P)return '';
  const src=pathsOk()?D.paths.src:pathsStale()?'the paths worked out here ('+(D.paths.src||'the .pth')+' is for another version of the map)':'the paths worked out here (no .pth)',n0=P.n0!=null?P.n0:P.n;
  const pn=PN_ENTS,i=pn.indexOf(ei);if(i<0)return '';
  let h='<h4>AI paths (ai_showroutes)</h4>';
  if(pn.length!==n0)return h+'<div class="note warn">'+esc(src)+' has '+n0+' nodes but the map has '+pn.length+' info_pathnode: it was made for another version of the map (the game rebuilds it).</div>';
  const O=P.o,F=P.f,C=P.c,fh=CVARS.ai_fallheight,nc=C.length/9;
  const out=new Map(),inn=new Map();
  for(let k=0;k<nc;k++){const a=C[k*9]|0,b=C[k*9+1]|0,f=C[k*9+2];if(a===i)out.set(b,f);if(b===i)inn.set(a,f);}
  const two=[],to=[],from=[];
  for(const[b,f]of out){if(inn.has(b)&&inn.get(b)<fh&&f<=fh)two.push([b,f]);else to.push([b,f]);}
  for(const[a,f]of inn)if(!(out.has(a)&&f<fh&&out.get(a)<=fh))from.push([a,f]);
  const lst=a=>a.slice(0,60).map(([n,f])=>(n<n0?linkEnt(pn[n]):'<b>new node '+(n-n0+1)+'</b> (Modify)')+(f?' <span class="co">drop '+f+(f>fh?', past ai_fallheight':'')+'</span>':'')).join(', ')+(a.length>60?', \u2026 '+(a.length-60)+' more':'');
  h+='<div class="note">node '+i+' of '+n0+' in '+esc(src)+(P.n>n0?', with '+(P.n-n0)+' new from Modify':'')+', dropped to the floor at '+esc(fvec([O[i*3],O[i*3+1],O[i*3+2]]))+
     ((F[i]&1)?' \u00b7 DONT_LINK: the game never connects it':'')+'</div>';
  if(!out.size&&!inn.size)h+='<div>no paths'+((F[i]&1)?'':' (ai_showroutes draws a red X here)')+'</div>';
  if(two.length)h+='<div>both ways ('+two.length+'): '+lst(two)+'</div>';
  if(to.length)h+='<div>one way to ('+to.length+'): '+lst(to)+'</div>';
  if(from.length)h+='<div>one way from ('+from.length+'): '+lst(from)+'</div>';
  const iss=paIssueList(i);
  for(const x of iss)h+='<div class="'+(x.lv===0?'note':'warn')+'">'+esc(x.t)+'</div>';
  // the map's own node: room for a man on it (Modify's nodes have it in their issues)
  if(!(F[i]&1)&&!iss.some(x=>x.k==='wall')){const w=nodeWall([O[i*3],O[i*3+1],O[i*3+2]]);if(w)h+='<div class="warn">'+esc(nodeWallText(w))+'</div>';}
  return h;
}
// What a marker's colour (and a path node's outline) means, since MOHRadiant shows no legend.
function radiantNote(X,e){
  const sw=c=>'<span class="sw" style="background:rgb('+c.map(v=>Math.round(v*255)).join(',')+')"></span>';
  const node=e.cls==='info_pathnode';
  if(!node&&X.mk===1&&!X.standin)return '';
  let h='<h4>Colours (as in MOHRadiant)<span class="sp"></span><button class="sm" data-legend="1" title="Every colour, marker and editor surface (L)">Legend</button></h4>';
  if(X.standin)h+='<div>'+sw(X.ccol)+'a dark green 16-unit cube: MOHRadiant has no definition for '+esc(e.cls)+' ("Not found in source."), so it draws its stand-in</div>';
  if(X.mk!==1)h+='<div>'+sw(X.col)+'box: '+(X.mk===2?(node?'pink, ':'')+'its colour turned inside out because '+X.why:'flat, from '+X.why)+'</div>';
  if(node){
    const sf=parseInt(e.kvl.spawnflags||'0',10)|0, t=X.ol&&!nodeFlagsBad(sf)?NODE_OUTLINES.find(n=>sf&n[0]):null;
    h+='<div>'+(X.ol?sw(X.ol):'')+'border: '+(!X.ol?'none (a plain node)':t?esc(t[2]):'black, flags that don\'t go together')+'</div>';
  }
  return h;
}
function clipText(s){return s.length>6000?s.slice(0,6000)+'\n... ('+(s.length-6000)+' more characters - use Copy)':s;}
function infoPrim(pi){
  const p=SC.prims[pi],e=MAP.ents[p.ent],pr=e.prims[p.bn];
  const kind=p.kind===1?'patch':p.kind===2?'terrain':'brush';
  let h='<div><b>'+kind+' '+p.bn+'</b> of '+(p.ent?linkEnt(p.ent):'the world (worldspawn)')+'</div>';
  if(isFinite(p.mins[0])){
    h+='<h4>Bounds</h4>'+kvTable([['mins',esc(fvec(p.mins))],['maxs',esc(fvec(p.maxs))],['size',esc(fvec([p.maxs[0]-p.mins[0],p.maxs[1]-p.mins[1],p.maxs[2]-p.mins[2]]))],
      ['centre',esc(fvec([(p.mins[0]+p.maxs[0])/2,(p.mins[1]+p.maxs[1])/2,(p.mins[2]+p.maxs[2])/2]))]]);
    const c=[(p.mins[0]+p.maxs[0])/2,(p.mins[1]+p.maxs[1])/2,(p.mins[2]+p.maxs[2])/2], hs=[(p.maxs[0]-p.mins[0])/2,(p.maxs[1]-p.mins[1])/2,(p.maxs[2]-p.mins[2])/2];
    const sc='// a trigger covering this '+kind+'\nlocal.trig = spawn trigger_multiple\nlocal.trig.origin = '+fvec(c)+'\nlocal.trig setsize '+fvec(hs.map(v=>-v))+' '+fvec(hs);
    h+='<h4>Script<span class="sp"></span>'+copyBtn(sc)+'</h4><pre>'+esc(sc)+'</pre>';
  }
  if(p.kind===1){const d=pr.d;h+='<h4>Patch</h4>'+kvTable([['texture','<a data-tex="'+texFor(d.tex).i+'">'+esc(d.tex)+'</a>'],['grid',d.w+' x '+d.h+' control points'],
    ['contents',esc(bitNames(d.cont,CF_NAMES).join(' ')||'0')],['surface',esc(bitNames(d.flags,SF_NAMES).join(' ')||'0')]]);}
  else if(p.kind===2){const d=pr.d;h+='<h4>Terrain</h4>'+kvTable([['grid',d.W+' x '+d.H+' vertices ('+((d.W-1)*64)+' x '+((d.H-1)*64)+' units)'],['origin',esc(fvec(d.org))],
    ['textures',esc([...new Set(d.corners.filter(c=>!c.miss).map(c=>c.tex))].join(', '))]]);}
  else{
    for(let f=p.f0;f<p.f1;f++)h+=faceHtml(f,lastHit&&lastHit.face===f);
  }
  h+='<h4>.map source<span class="sp"></span>'+copyBtn(srcText(pr.ts,pr.te),'Copy')+openBtn(pr.ts)+'</h4><pre>'+esc(clipText(srcText(pr.ts,pr.te)))+'</pre>';
  card(kind+' '+p.bn+(p.ent?' · entity '+p.ent:' · world'),h);
}
function faceHtml(f,hit){
  const p=SC.prims[SC.facePrim[f]],e=MAP.ents[p.ent],pr=e.prims[p.bn],te=TEX[SC.faceTex[f]];
  if(SC.faceKind[f]!==0)return '<div class="face'+(hit?' hit':'')+'">'+(hit?'<b>clicked: </b>':'')+esc(te.n.replace(/^textures\//,''))+'</div>';
  const fd=pr.d.faces[SC.faceSide[f]];if(!fd)return '';
  const pl=SC.facePlane[f];
  let s='<div class="face'+(hit?' hit':'')+'">'+(hit?'<b>clicked face</b> · ':'face '+SC.faceSide[f]+' · ')+'<a data-tex="'+te.i+'">'+esc(fd.tex)+'</a>'+(te.f&TF_MISSING?' <span style="color:var(--err)">(not in the paks)</span>':'');
  s+='<div class="co">'+(fd.tm?'brush-primitive texture matrix':'shift '+fnum(fd.sh[0])+' '+fnum(fd.sh[1])+' · scale '+fd.sc[0]+' '+fd.sc[1]+' · rotate '+fnum(fd.rot))+
    ' · normal '+fvec(pl.slice(0,3).map(v=>Math.round(v*1000)/1000))+'</div>';
  const cf=bitNames(fd.cont,CF_NAMES),sf=bitNames(fd.flags,SF_NAMES);
  if(cf.length||sf.length)s+='<div class="co">'+(cf.length?'contents: '+esc(cf.join(' ')):'')+(sf.length?(cf.length?' · ':'')+'surface: '+esc(sf.join(' ')):'')+'</div>';
  if(te.p&&te.p.length)s+='<div class="co">shader surfaceparms: '+esc(te.p.join(' '))+'</div>';
  if(hit&&te.img)s+='<div class="co">image: '+esc(te.img)+(te.w?' ('+te.w+' x '+te.h+')':'')+'</div>';
  return s+'</div>';
}
function infoFace(h){
  const f=h.face,te=TEX[SC.faceTex[f]];
  let s='';
  if(TEXURL[te.i])s+='<div style="margin:4px 0"><img src="'+TEXURL[te.i]+'" style="max-width:128px;max-height:128px;border:1px solid var(--line);border-radius:4px"></div>';
  s+=faceHtml(f,true);
  if(h.point)s+='<div class="note">clicked at '+esc(fvec(h.point))+copyBtn(fvec(h.point))+'</div>';
  s+=kvTable([['shader',esc(te.n)],['flags',esc([te.g,te.f&TF_SKY?'sky':'',te.f&TF_NODRAW?'nodraw':'',te.f&TF_ALPHATEST?'alpha-tested':'',te.f&TF_BLEND?'blended':'',te.f&TF_ADD?'additive':'',te.f&TF_MISSING?'missing':''].filter(Boolean).join(' ')||'-')],
    ['used on',(texCounts().find(x=>x[0]===te.i)||[0,0])[1]+' faces / surfaces']]);
  s+='<div class="row"><button class="sm" data-tex="'+te.i+'">Select every brush with this texture</button></div>';
  card('Texture: '+te.n.replace(/^textures\//,''),s);
}
function infoMulti(ents,prims){
  let h='<div><b>'+SEL.size+'</b> selected</div>';
  const b=selBounds();
  if(b)h+='<h4>Combined bounds</h4>'+kvTable([['mins',esc(fvec(b.mins))],['maxs',esc(fvec(b.maxs))],['size',esc(fvec([b.maxs[0]-b.mins[0],b.maxs[1]-b.mins[1],b.maxs[2]-b.mins[2]]))]]);
  if(ents.length){
    const lines=[];
    h+='<h4>Entities ('+ents.length+')<span class="sp"></span>'+copyBtn('','Copy as script')+'</h4><table>';
    for(const ei of ents.slice(0,400)){const e=MAP.ents[ei],X=ENTS[ei],bx=X.box;
      h+='<tr><td>'+linkEnt(ei)+'</td><td class="co">'+(bx?esc(fvec(bx.origin)):'')+'</td></tr>';
      if(bx)lines.push((e.kvl.targetname?'$'+e.kvl.targetname:'// '+e.kvl.classname+' entity '+ei)+' origin '+fvec(bx.origin)+' setsize '+fvec(bx.mins)+' '+fvec(bx.maxs));}
    h+='</table>'+(ents.length>400?'<div class="note">... and '+(ents.length-400)+' more</div>':'');
    h=h.replace('data-copy=""','data-copy="'+esc(lines.join('\n'))+'"');
    if(ents.length===2){const A=ENTS[ents[0]].anchor,Bv=ENTS[ents[1]].anchor;if(A&&Bv)h+='<div class="note">distance between the two: '+fnum(Math.hypot(A[0]-Bv[0],A[1]-Bv[1],A[2]-Bv[2]))+' units</div>';}
  }
  if(prims.length)h+='<h4>Brushes ('+prims.length+')</h4><div class="note">'+prims.slice(0,60).map(pi=>{const p=SC.prims[pi];return (p.kind===1?'patch ':p.kind===2?'terrain ':'brush ')+p.bn+(p.ent?'/e'+p.ent:'');}).join(', ')+(prims.length>60?' ...':'')+'</div>';
  card(SEL.size+' selected',h);
}
$('infoBody').addEventListener('click',e=>{
  const c=e.target.closest('[data-copy]');if(c){copyText(c.getAttribute('data-copy'));return;}
  const om=e.target.closest('[data-openmap]');if(om){openMapAt(+om.getAttribute('data-openmap'));return;}
  const g=e.target.closest('[data-go]');if(g){const v=vecNums(g.getAttribute('data-go')),f=vecNums(g.getAttribute('data-from')||'');
    if(v.length>=3)flyLook([v[0],v[1],v[2]],256,f.length>=3?[f[0],f[1],f[2]]:null);return;}
  const s=e.target.closest('[data-sel]');if(s){const ei=+s.getAttribute('data-sel');SEL.clear();SEL.add('e'+ei);lastHit=null;selectionChanged();focusSelection();showInfo('sel');return;}
  const os_=e.target.closest('[data-openscr]');if(os_){openScr(+os_.getAttribute('data-openscr'));return;}
  const sp=e.target.closest('[data-selprims]');if(sp){SEL.clear();for(const pi of sp.getAttribute('data-selprims').split(','))SEL.add('p'+pi);lastHit=null;selectionChanged();focusSelection();
    if(infoMode!=='leak'){const t=$('infoBody').scrollTop;leakCard();$('infoBody').scrollTop=t;}flash('The brushes either side of the gap are selected (N: their info)');return;}
  const t=e.target.closest('[data-tex]');if(t){selectByTexture(+t.getAttribute('data-tex'),false);selectionChanged();return;}
  const pa=e.target.closest('[data-path]');if(pa){const ei=+pa.getAttribute('data-path');selectPath({ent:ei,face:-1,prim:-1,point:null},false);return;}
  if(e.target.closest('[data-legend]'))toggleLegend(true);
});

// ============================================================================
//  The legend (L): what the colours, markers and editor surfaces mean
// ============================================================================
// Built once from the table the build puts in the page (LEGEND in mohaa_map_view.py, the
// same one the launcher's Help > Legend shows), with the editor pictures of its textures.
const legOv=$('legOv');
function toggleLegend(force){
  const show=(force!==undefined)?force:(legOv.style.display==='none');
  if(show&&!legOv.dataset.built){buildLegend();legOv.dataset.built='1';}
  if(show)toggleHelp(false);
  legOv.style.display=show?'flex':'none';
}
function legendSwatch(r,thumbs){
  const rgb=c=>'rgb('+(c||[0.5,0.5,0.5]).map(v=>Math.round(Math.max(0,Math.min(1,v))*255)).join(',')+')';
  switch(r.sw){
    case 'node':return '<span class="lsw" style="background:'+rgb(r.fill)+(r.line?';box-shadow:inset 0 0 0 3px '+rgb(r.line):'')+'"></span>';
    case 'diamond':return '<span class="lsw lnone"><i class="dia" style="background:'+rgb(r.fill)+'"></i></span>';
    case 'wire':return '<svg class="lsw ldark" viewBox="0 0 24 24"><path d="M3.5 8.5H15.5V20.5H3.5ZM8.5 3.5H20.5V15.5H8.5ZM3.5 8.5L8.5 3.5M15.5 8.5L20.5 3.5M15.5 20.5L20.5 15.5M3.5 20.5L8.5 15.5" stroke="'+rgb(r.fill)+'" stroke-width="1.5" fill="none"/></svg>';
    case 'arrow':return '<svg class="lsw ldark" viewBox="0 0 24 24"><path d="M3 12H19M19 12L14.5 7.5M19 12L14.5 16.5" stroke="#fff" stroke-width="2.6" fill="none"/></svg>';
    case 'link':return '<svg class="lsw ldark" viewBox="0 0 24 24"><path d="M4 19L20 5" stroke="'+rgb(r.fill)+'" stroke-width="1.5"/><path d="M15.5 6.8L20 5L18.2 9.5Z" fill="'+rgb(r.fill)+'"/></svg>';
    case 'label':return '<span class="lsw llab">Aa</span>';
    case 'lines':return '<svg class="lsw ldark" viewBox="0 0 24 24">'+(r.lines||[]).map(l=>'<path d="M'+l[0]+' '+l[1]+'L'+l[2]+' '+l[3]+'" stroke="'+rgb(l[4])+'" stroke-width="1.4" fill="none"/>').join('')+'</svg>';
    case 'sel':return '<span class="lsw lsel"></span>';
    case 'hover':return '<span class="lsw lhov"></span>';
    case 'tex':{const u=thumbs[r.tex];const te=TEXI.get(r.tex);
      return u?'<img class="lsw" src="'+u+'" alt="">':'<span class="lsw" style="background:'+rgb(r.fill||(te&&te.c))+'"></span>';}
    default:return '<span class="lsw" style="background:'+rgb(r.fill)+'"></span>';
  }
}
function buildLegend(){
  const L=D.legend||{s:[],t:{}}, thumbs={};
  for(const k in (L.t||{})){const v=L.t[k];thumbs[k]=URL.createObjectURL(new Blob([D.bytes(v[0])],{type:v[1]||'image/png'}));}
  // one column per section, each scrolling on its own under its heading (see #legBody)
  let h='';
  for(const sec of L.s||[]){
    h+='<div class="sec"><h4>'+esc(sec.title)+'</h4>'+(sec.note?'<div class="note">'+esc(sec.note)+'</div>':'');
    for(const r of sec.rows){
      if(r.sub){h+='<div class="sub">'+esc(r.sub)+'</div>';continue;}
      h+='<div class="lrow"><span class="s">'+legendSwatch(r,thumbs)+'</span><div><span class="nm">'+esc(r.name)+'</span>'+
         (r.key?'<span class="k">'+esc(r.key)+'</span>':'')+'<div class="ds">'+esc(r.desc||'')+'</div></div></div>';
    }
    h+='</div>';
  }
  $('legBody').innerHTML=h||'<div class="note">This page was built without a legend.</div>';
}
$('legClose').onclick=()=>toggleLegend(false);
legOv.addEventListener('click',e=>{if(e.target===legOv)toggleLegend(false);});
$('bLegend').onclick=()=>toggleLegend();
$('hintHelp').onclick=()=>toggleHelp();
$('hintLeg').onclick=()=>toggleLegend();

// ============================================================================
//  MODIFY: new entities, the AI's paths to new path nodes, saving a new .bsp / .map
// ============================================================================
// Entities added here are temporary until saved: drawn see-through, kept out of the map's
// own lists, clickable in the 3D view and in MODIFY's list. A new info_pathnode joins the
// AI's paths as soon as it is placed (not while its parameters are open or its origin is
// being trimmed): its links are worked out the way the game makes its .pth (pgLink, both
// ways with every node near it), on top of the map's own .pth; a map without a .pth gets
// all of its paths worked out the first time. Save as .bsp writes a copy of the .bsp with
// the new entities in its entity lump (the launcher does it, mohaa_bsp.write_bsp_entities);
// Save as .map writes the .map with them added.
const MOD={cls:'info_pathnode',ents:[],sel:-1,nid:1,trim:false,edit:-1,flash:{},stepI:4,placing:null,ghost:null,edPos:null,
  multi:new Set(),undo:[],redo:[]};
const MOD_STEPS=[1,2,3,4,5,8,10,12,16,20,25,32,40,50];
let PA_C=null,PA_GEN=null,PA_PEND=false;
function modKv(m,k){for(const[a,v]of m.kv)if(a.toLowerCase()===k)return v;return null;}
function modSetKv(m,k,v){const i=m.kv.findIndex(x=>x[0].toLowerCase()===k);if(i>=0)m.kv[i][1]=v;else m.kv.push([k,v]);}
// Yaw (Alt+R): the selected entity turned to the next of 0, 90, 180 and 270 degrees, after the
// one it faces now (a yaw that is none of them, or no angle at all, starts at 0). An info_
// class (path nodes, waypoints, player starts...) gets "angle" "<yaw>", anything else "angles"
// "0 <yaw> 0"; the other of the two keys is taken out, so only the new one counts. Every
// selected row turns to the same yaw, and each press is one Undo step.
const MOD_YAWS=[0,90,180,270];
function modYaw(){
  const m=MOD.ents[MOD.sel];if(!m){flash('Select an entity in Modify first (Alt+R Yaw)');return;}
  const L=modSelEnts(false).filter(x=>!x.del);if(!L.length)return;
  const kv=modKvl(m);let cur=null;
  if(kv.angles!=null){const a=parseVec(kv.angles,3);if(a)cur=a[1];}
  else if(kv.angle!=null&&isFinite(parseFloat(kv.angle)))cur=parseFloat(kv.angle);
  if(cur!=null)cur=((cur%360)+360)%360;
  const k=cur==null?-1:MOD_YAWS.indexOf(cur),yaw=k<0?0:MOD_YAWS[(k+1)%4];
  if(MOD.edit>=0)modEditClose(true);
  modHist();let node=false;
  for(const x of L){
    const info=modCls(x).startsWith('info_'),drop=info?'angles':'angle';
    if(info)modSetKv(x,'angle',String(yaw));else modSetKv(x,'angles','0 '+yaw+' 0');
    const i=x.kv.findIndex(p=>p[0].toLowerCase()===drop);if(i>=0)x.kv.splice(i,1);
    if(modIsNode(x))node=true;}
  modChanged(node);
  flash((L.length===1?modName(m):L.length+' entities')+': yaw '+yaw+' (Alt+R again: '+MOD_YAWS[(MOD_YAWS.indexOf(yaw)+1)%4]+')');
}
function modOrigin(m){return parseVec(modKv(m,'origin'),3)||[0,0,0];}
function modCls(m){return(modKv(m,'classname')||'').toLowerCase();}
function modSf(m){return parseInt(modKv(m,'spawnflags')||'0',10)|0;}
function modIsNode(m){return modCls(m)==='info_pathnode';}
// an entry for one of the map's own entities (m.ei), and whether it differs from the map
function modIsMap(m){return m.ei!=null;}
function modKvEdited(m){
  if(m.ei==null)return true;
  const a=m.kv,b=m.orig;if(!b||a.length!==b.length)return true;
  for(let i=0;i<a.length;i++){if(a[i][0]!==b[i][0]||a[i][1]!==b[i][1])return true;}
  return false;}
function modEdited(m){
  // same answer as comparing JSON.stringify(kv) with JSON.stringify(orig), without building two strings per call
  if(m.ei==null||m.del)return true;
  const a=m.kv,b=m.orig;if(!b||a.length!==b.length)return true;
  for(let i=0;i<a.length;i++){if(a[i][0]!==b[i][0]||a[i][1]!==b[i][1])return true;}
  return false;}
// drawn by Modify (and the map's own marker hidden): new ones, changed ones, and any being edited
function modDrawn(i){const m=MOD.ents[i];return !!m&&!m.hid&&!m.del&&(!modIsMap(m)||modEdited(m)||modBusy(i));}
// the map's entities Modify draws instead (entShown leaves their markers out)
let MOD_HID=new Set();
function modHideSync(){
  // (a hidden row hides the map's own marker too)
  const s=new Set();MOD.ents.forEach((m,i)=>{if(modIsMap(m)&&(modDrawn(i)||m.hid||m.del))s.add(m.ei);});
  const same=s.size===MOD_HID.size&&[...s].every(x=>MOD_HID.has(x));
  if(same)return;MOD_HID=s;
  if(gl){rebuildMarkers();rebuildModels();lineDirty=true;}
}
// a map entity Modify can take: a point entity with an origin in the entity lump (not the
// world or a brush entity, not a static prop, not one the level script spawns)
function modKvl(m){const k={};for(const[a,v]of m.kv){const l=a.toLowerCase();if(!(l in k))k[l]=v;}return k;}
// Modify's target links, drawn with the map's (Links, 7; arrowheads by drawLinkHeads): from
// each of its entities to what its "target" names, and from the map's entities to them
function modLinks(H,L,sc,selE){
  if(!MOD.ents.length)return;
  const push=(A,B,col,hot)=>{const c=hot?[sc[0],sc[1],sc[2],1]:[col[0],col[1],col[2],0.75];
    (hot?H:L).push(A[0],A[1],A[2],c[0],c[1],c[2],c[3],B[0],B[1],B[2],c[0],c[1],c[2],c[3]);LINKS.push([A,B,c,hot]);};
  const drawn=[];MOD.ents.forEach((m,i)=>{if(modDrawn(i))drawn.push([m,i,modKvl(m)]);});
  for(const[m,i,k]of drawn){const o=modOrigin(m),col=modLook(m).col;
    if(k.target){
      for(const ti of ENTS.tn.get(k.target)||[]){const Y=ENTS[ti];if(Y.anchor&&entVisible(ti))push(o,Y.anchor,col,i===MOD.sel||selE.has(ti));}
      for(const[m2,j,k2]of drawn)if(j!==i&&k2.targetname===k.target)push(o,modOrigin(m2),col,i===MOD.sel||j===MOD.sel);}
    // the map's entities whose target is this one
    if(k.targetname)for(const X of ENTS){if(!X.anchor||MAP.ents[X.ei].kvl.target!==k.targetname||!entVisible(X.ei))continue;
      push(X.anchor,o,X.col,selE.has(X.ei)||i===MOD.sel);}
  }
}
// ---- Make path: the selected entity's "target" set to the next entity clicked -------------
// Only an entity that has a targetname can be clicked (the selected one needs none). The
// clicked one is selected after, so Make path again goes on along the path.
function modLinkStart(){
  if(MOD.linking){modLinkCancel();return;}
  const m=MOD.ents[MOD.sel];if(!m)return;
  if(MOD.placing)modPlaceCancel();if(MOD.trim)modTrim(false);if(MOD.edit>=0)modEditClose(true);
  MOD.linking={from:m};modRender();
  flash('Make path: click an entity with a targetname for '+modName(m)+'\'s "target" to point at (Esc cancels)');
}
function modLinkCancel(){if(!MOD.linking)return;MOD.linking=null;modRender();flash('No target set');}
function modLinkClick(x,y){
  const L=MOD.linking;if(!L)return false;
  const src=L.from,si=MOD.ents.indexOf(src);if(si<0){modLinkCancel();return true;}
  let to=null,toEi=-1,hit=null;
  const mi=modPick(x,y);
  if(mi>=0)to=MOD.ents[mi];
  else{const h=hitInfo(pickAt(x,y),x,y);hit=h;const ei=h?h.ent:-1;
    if(!(ei>0)||isWorldlike(ei)){flash('Click an entity (Esc cancels)');return true;}
    to=MOD.ents.find(m=>m.ei===ei)||null;if(!to)toEi=ei;}
  if(to===src||(toEi>=0&&src.ei===toEi)){flash('An entity can\'t target itself: click another (Esc cancels)');return true;}
  let name=to?modKv(to,'targetname'):MAP.ents[toEi].kvl.targetname;
  // a target needs a targetname to point at: the one clicked must have one already (the
  // selected one needs none)
  if(!name){flash((to?modName(to):entName(toEi))+' has no targetname, so nothing can target it: click one that has one, or give it a "targetname" first (Esc cancels)');return true;}
  modHist();modSetKv(src,'target',name);
  MOD.linking=null;
  // the clicked one is selected next, to go on along the path
  if(to&&!modIsMap(to))modSelect(MOD.ents.indexOf(to));
  else if(hit)clickSelect(hit,{});
  modChanged(false);lineDirty=true;
  flash(modName(src)+' now targets $'+name+' (Make path again to go on from here)');
  return true;
}
function modTakes(ei){
  if(!(ei>0)||ei>=MAP.ents.length)return false;
  const e=MAP.ents[ei],X=ENTS[ei],fs=(D.bsp&&D.bsp.firstStatic!=null)?D.bsp.firstStatic:(MAP.nMap||MAP.ents.length);
  return !e.scr&&!WORLDLIKE[e.cls]&&!X.hasGeo&&!!X.origin&&ei<fs;
}
// the selection changed: a map entity Modify can take gets a row (until something else is
// selected, unless it was changed)
function modSyncSel(){
  if(!MOD||!$('modList'))return;
  const ei=selFocusEnt(),cur=MOD.ents[MOD.sel],keep=new Set();
  MOD.ents.forEach((m,i)=>{if(!modIsMap(m)||modEdited(m)||modBusy(i)||m.hid||m.del||m.ei===ei)keep.add(m);});
  const edit=MOD.ents[MOD.edit],mv=MOD.placing&&MOD.placing.move!=null?MOD.ents[MOD.placing.move]:null;
  MOD.ents=MOD.ents.filter(m=>keep.has(m));
  let sel=cur&&keep.has(cur)?cur:null;
  if(modTakes(ei)){let m=MOD.ents.find(x=>x.ei===ei);
    if(!m){const kv=MAP.ents[ei].kv.map(x=>[x[0],x[1]]);m={id:MOD.nid++,ei:ei,kv:kv,orig:kv.map(x=>x.slice())};MOD.ents.push(m);}
    sel=m;}
  else if(cur&&modIsMap(cur)&&!SEL.size)sel=null;
  MOD.sel=sel?MOD.ents.indexOf(sel):-1;
  if(edit)MOD.edit=MOD.ents.indexOf(edit);
  if(mv)MOD.placing.move=MOD.ents.indexOf(mv);
  modRender();
}
// a temporary node is part of the paths unless it is being edited or trimmed
function modBusy(i){const m=MOD.ents[i],P=MOD.placing;
  return MOD.edit===i||(MOD.trim&&modIsSel(i))||(!!P&&P.move!=null&&(P.move===i||(!!P.group&&P.group.includes(m))));}
// ---- the selection: one entity or several ---------------------------------------------------
// MOD.sel is the one the single-entity buttons act on (Edit parameters, Make path, Eye view,
// Fly to); MOD.multi holds the others Shift+click added. Copy, Move, Trim origin and Delete
// take them all, and with Copy, Move and Trim origin also the map's own entities selected in
// the view that Modify can take (each gets its row).
function modIsSel(i){const m=MOD.ents[i];return !!m&&(i===MOD.sel||MOD.multi.has(m));}
function modRowFor(ei){let m=MOD.ents.find(x=>x.ei===ei);
  if(!m){const kv=MAP.ents[ei].kv.map(x=>[x[0],x[1]]);m={id:MOD.nid++,ei:ei,kv:kv,orig:kv.map(x=>x.slice())};MOD.ents.push(m);}
  return m;}
function modSelEnts(withMap){
  const out=[],cur=MOD.ents[MOD.sel];if(cur)out.push(cur);
  for(const m of MOD.ents)if(m!==cur&&MOD.multi.has(m))out.push(m);
  if(withMap)for(const ei of selectedEnts())if(modTakes(ei)){const m=modRowFor(ei);if(!out.includes(m))out.push(m);}
  return out;}
// how many a Copy / Move / Trim origin would take (without making the map's rows)
function modSelCount(){let n=modSelEnts(false).length;
  for(const ei of selectedEnts())if(modTakes(ei)){const m=MOD.ents.find(x=>x.ei===ei);if(!m||!modIsSel(MOD.ents.indexOf(m)))n++;}
  return n;}
function modMultiPrune(){for(const m of[...MOD.multi])if(!MOD.ents.includes(m)||MOD.ents[MOD.sel]===m)MOD.multi.delete(m);}
// Shift+click on an added entity (in the view or its row): into the selection, or out of it
function modToggleSel(i){const m=MOD.ents[i];if(!m)return;
  if(MOD.trim||(MOD.placing&&MOD.placing.move!=null)){flash('Finish moving or trimming first');return;}
  if(i===MOD.sel){const next=MOD.ents.findIndex(x=>MOD.multi.has(x));
    if(next>=0){MOD.multi.delete(MOD.ents[next]);MOD.sel=next;modRender();requestDraw();}else modDeselect();return;}
  if(MOD.multi.has(m)){MOD.multi.delete(m);modRender();requestDraw();return;}
  if(MOD.sel<0){modSelect(i);return;}
  MOD.multi.add(m);modRender();requestDraw();
  flash((MOD.multi.size+1)+' selected: Copy, Move, Trim origin and Delete take them all');}

// ---- Undo / Redo: every change to Modify's entities, back to none added -------------------
// Each change keeps the state before it (modHist): placing, moving, Trim origin (all its key
// presses one step), Edit parameters (once closed), Make path, Copy, Delete and Restore. Hiding
// isn't a change (Ctrl+Z undoes that). Undo and Redo first finish whatever is under way.
// (history is kept as compact JSON strings, one per step; nothing is dropped)
function modSnap(){return{ents:MOD.ents.map(m=>({id:m.id,ei:m.ei,kv:m.kv.map(x=>x.slice()),orig:m.orig?m.orig.map(x=>x.slice()):null,hid:!!m.hid,del:!!m.del})),
  sel:MOD.ents[MOD.sel]?MOD.ents[MOD.sel].id:null,multi:[...MOD.multi].map(m=>m.id)};}
function modHist(s){MOD.undo.push(JSON.stringify(s||modSnap()));MOD.redo.length=0;}
function modRestore(s){
  if(typeof s==='string')s=JSON.parse(s);
  MOD.ents=s.ents.map(e=>{const m={id:e.id,kv:e.kv.map(x=>x.slice())};
    if(e.ei!=null){m.ei=e.ei;m.orig=e.orig.map(x=>x.slice());}if(e.hid)m.hid=true;if(e.del)m.del=true;return m;});
  const by=new Map(MOD.ents.map(m=>[m.id,m])),cur=by.get(s.sel);
  MOD.sel=cur?MOD.ents.indexOf(cur):-1;MOD.multi=new Set(s.multi.map(id=>by.get(id)).filter(Boolean));MOD.edit=-1;
}
function modUndoGo(d){
  if(MOD.edit>=0)modEditClose(true);
  // a Copy not put down yet: Undo takes just that away
  if(MOD.placing){const cp=!!MOD.placing.copy;modPlaceCancel();if(cp&&d<0)return;}
  if(MOD.trim)modTrim(false);
  if(MOD.linking)modLinkCancel();
  const from=d<0?MOD.undo:MOD.redo,to=d<0?MOD.redo:MOD.undo;
  if(!from.length){flash(d<0?'Nothing to undo in Modify':'Nothing to redo in Modify');return;}
  to.push(JSON.stringify(modSnap()));modRestore(from.pop());
  modChanged(true);lineDirty=true;
  flash((d<0?'Undone':'Redone')+': '+MOD.undo.length+' more to undo, '+MOD.redo.length+' to redo');
}
// its box: "setsize", else its model's size, else its class's editor box, else 16 units
function modBox(m){
  const ss=parseVec(modKv(m,'setsize'),6);if(ss)return{mins:ss.slice(0,3),maxs:ss.slice(3)};
  const mdl=(modKv(m,'model')||'').toLowerCase().replace(/\\/g,'/');
  if(mdl){const M=(D.models||[]).find(M=>M.p&&(M.p.toLowerCase()===mdl||M.p.toLowerCase()==='models/'+mdl));
    if(M){if(M.ss)return{mins:M.ss[0],maxs:M.ss[1]};const sc=parseFloat(modKv(m,'scale'))||1;
      return{mins:M.b[0].map(v=>v*sc),maxs:M.b[1].map(v=>v*sc)};}}
  // as the map's own markers (entityBox): MOHRadiant's 16-unit stand-in, else the class's box
  const X=modLook(m);if(X.standin)return{mins:[-8,-8,-8],maxs:[8,8,8]};
  const d=X.def;if(d&&d.b)return{mins:d.b[0],maxs:d.b[1]};
  return{mins:[-8,-8,-8],maxs:[8,8,8]};
}
// its marker's look, as buildEntities / radiantLook give a map entity of the same keys:
// colour (a path node: MOHRadiant's dark green stand-in, turned inside out with a
// targetname) and the spawnflags outline
function modLook(m){
  const kvl={};for(const[k,v]of m.kv){const kl=k.toLowerCase();if(!(kl in kvl))kvl[kl]=v;}
  const e={cls:modCls(m),kv:m.kv,kvl:kvl},def=(D.defs||{})[e.cls]||null;
  const X={ei:-1,def:def,col:def&&def.c?def.c:[0.6,0.6,0.6]};
  radiantLook(X,e);return X;
}
function modColour(m){const X=modLook(m);return X.mcol||X.col;}
// ---- Modify's entities with their model ---------------------------------------------------
// The .tik it draws, as the map build picks one for a map entity (entity_model_path): its
// "model" key, else its class's .tik (the /*QUAKED*/ header the class came from), else a
// classname that is a model path. '' for none (a brush model "*N" too).
function modTik(m){
  let p=(modKv(m,'model')||'').toLowerCase().replace(/\\/g,'/').trim();
  if(p.startsWith('*'))return '';
  if(!p){const d=(D.defs||{})[modCls(m)];if(d&&d.t)p=String(d.t).toLowerCase();}
  if(!p){const c=modCls(m);if(c.includes('/'))p=c;}
  if(!p)return '';
  while(p.includes('//'))p=p.replace('//','/');
  if(!p.startsWith('models/'))p='models/'+p;
  if(!/\.(tik|skd|skb)$/.test(p))p+='.tik';
  return p;
}
// Its mesh (one per model, its own instance buffer): the map's when the map places that
// model, else built by the launcher from the paks (mohaa-sim-build, as Simulate's). null
// until it is here, or when it can't be drawn (in a browser: only the map's own models);
// the box is drawn meanwhile.
function modModelR(p){
  if(!gl||!p)return null;
  if(!MOD.mr)MOD.mr=new Map();
  if(MOD.mr.has(p))return MOD.mr.get(p);
  // (asked for in the middle of a draw: modelR binds its index buffer, which would land in
  // whichever vertex array is bound, so none is while it runs)
  const build=(M,A)=>{const prev=gl.getParameter(gl.VERTEX_ARRAY_BINDING);gl.bindVertexArray(null);
    let r=null;try{r=modelR(M,A);}catch(_e){r=null;}gl.bindVertexArray(prev);return r;};
  let R=null;
  const mi=(D.models||[]).findIndex(M=>String(M.p||'').toLowerCase()===p);
  if(mi>=0){R=build(D.models[mi],D);MOD.mr.set(p,R);return R;}
  if(SIM.src&&SIM.src.has(p)){const s=SIM.src.get(p);R=build(s[0],s[1]);MOD.mr.set(p,R);return R;}
  if(SIM.fail.has(p)||!/\.tik$/.test(p)){MOD.mr.set(p,null);return null;}
  if(!MOD.mwant)MOD.mwant=new Set();
  if(!MOD.mwant.has(p)){MOD.mwant.add(p);if(!simPost('mohaa-sim-build\n'+p)){MOD.mwant.delete(p);MOD.mr.set(p,null);}}
  return null;
}
// one instance: its placement (angles, scale), the light grid's light there, not pickable
// (a click finds it by its box, modPick)
function modInst(m){
  const kvl={};for(const[k,v]of m.kv){const kl=k.toLowerCase();if(!(kl in kvl))kvl[kl]=v;}
  const ax=anglesAxis(entAngles(kvl)),s=parseFloat(kvl.scale)||1,o=modOrigin(m),G=lightGrid();let c=[255,255,255];
  if(G){const v=lgFast(G,o).slice(0,3).map(x=>x*2),mx=Math.max(v[0],v[1],v[2]);c=mx>255?v.map(x=>x*255/mx):v;}
  return [ax[0][0]*s,ax[1][0]*s,ax[2][0]*s,o[0], ax[0][1]*s,ax[1][1]*s,ax[2][1]*s,o[1], ax[0][2]*s,ax[1][2]*s,ax[2][2]*s,o[2],
    0, c[0]/255,c[1]/255,c[2]/255, -1, -1, 0];
}
// the models of the drawn Modify entities, their instance buffers filled again only when a
// placement changed
function modModelsInst(){
  if(!gl)return [];
  const G=new Map();
  MOD.ents.forEach((m,i)=>{if(!modDrawn(i))return;const R=modModelR(modTik(m));if(!R)return;
    let l=G.get(R);if(!l){l=[];G.set(R,l);}l.push(m);});
  const out=[];
  for(const[R,list]of G){
    const key=list.map(m=>modOrigin(m).join(',')+'|'+(modKv(m,'angles')||'')+'|'+(modKv(m,'angle')||'')+'|'+(modKv(m,'scale')||'')).join(';');
    if(R.modKey!==key){R.modKey=key;const a=[];for(const m of list)a.push(...modInst(m));
      gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a),gl.DYNAMIC_DRAW);R.n=list.length;}
    out.push(R);}
  if(MOD.mr)for(const R of MOD.mr.values())if(R&&!G.has(R)){R.n=0;R.modKey='';}
  return out;
}
// whether Modify's entity m is drawn with its model (then its box is only outlined)
function modHasModel(m){const p=modTik(m);return !!(p&&MOD.mr&&MOD.mr.get(p));}
function modText(m){return '{\n'+m.kv.map(([k,v])=>'"'+k+'" "'+v+'"').join('\n')+'\n}';}
function modName(m){const tn=modKv(m,'targetname');return(modKv(m,'classname')||'?')+(tn?' $'+tn:'');}

// ---- the paths with the new nodes (PA: n, o, f, c as the .pth's arrays) ------------------
function paBase(){
  if(pathsOk()){const P=D.paths;return{n:P.n,o:D.f32(P.o),f:D.i32(P.f),c:D.f32(P.c)};}
  if(PA_GEN)return PA_GEN;
  return null;
}
// a map with no .pth: its own nodes' paths, made once (the game does the same at load)
function paGenerate(){
  if(PA_GEN||pathsOk())return;
  const pn=pnEnts();
  const org=pn.map(ei=>ENTS[ei].origin?ENTS[ei].origin.slice():[0,0,0]),fl=pn.map(ei=>parseInt(MAP.ents[ei].kvl.spawnflags||'0',10)|0);
  const t0=performance.now(),G=pgCreate(org,fl);
  const O=new Float32Array(G.o.length*3);G.o.forEach((p,i)=>O.set(p,i*3));
  PA_GEN={n:G.o.length,o:O,f:Int32Array.from(G.f),c:Float32Array.from(G.c),gen:true,over:G.over||[],ms:Math.round(performance.now()-t0)};
  flash((pathsStale()?(D.paths.src||'The .pth')+' is for another version of this map (map_time differs)':'No .pth for this map')+
    ': its AI paths were worked out here ('+PA_GEN.n+' nodes, '+PA_GEN.ms+' ms)'+(PA_GEN.over.length?' · '+PA_GEN.over.length+' node'+(PA_GEN.over.length===1?'':'s')+' hit the 48-path limit (see their cards)':''));
}
function paOk(){return !!PA();}
function paDirty(){PA_C=null;ROUTES=null;PATHCELLS=null;NODELIST=null;requestDraw();}
function PA(){
  if(PA_C)return PA_C;
  const nodes=[];MOD.ents.forEach((m,i)=>{if(!modIsMap(m)&&modIsNode(m)&&!modBusy(i))nodes.push(m);});
  // no .pth: work the map's paths out first, a moment later so the note shows before it
  if(!pathsOk()&&!PA_GEN){
    if(!PA_PEND){PA_PEND=true;flash((pathsStale()?'The .pth is for another version of this map':'No .pth for this map')+': working out its AI paths...');
      setTimeout(()=>{try{paGenerate();}finally{PA_PEND=false;paDirty();}},40);}
    return null;}
  const B0=paBase();if(!B0)return null;
  // the map's own nodes Modify changed (not while being edited, moved or trimmed): node k
  // of the .pth is the map's k-th info_pathnode
  const pn=pnEnts(),edits=[];
  if(pn.length===B0.n)MOD.ents.forEach((m,i)=>{if(!modIsMap(m)||modBusy(i)||!modEdited(m))return;const k=pn.indexOf(m.ei);if(k>=0)edits.push([k,m]);});
  if(!nodes.length&&!edits.length)return PA_C=B0;
  const n0=B0.n,n=n0+nodes.length,O=new Float32Array(n*3),F=new Int32Array(n);
  O.set(B0.o.subarray(0,n0*3));F.set(B0.f.subarray(0,n0));
  const P=i=>[O[i*3],O[i*3+1],O[i*3+2]];
  const ek=new Set(edits.map(x=>x[0]));
  for(const[k,m]of edits){O.set(pgDrop(modOrigin(m)),k*3);
    F[k]=modIsNode(m)&&!m.del?modSf(m):1;                          // no longer a path node: no paths
    if(!(F[k]&1))for(let j=k-1;j>=0;j--)if(O[j*3]===O[k*3]&&O[j*3+1]===O[k*3+1]&&O[j*3+2]===O[k*3+2]){F[k]|=1;break;}}
  nodes.forEach((m,k)=>{const i=n0+k,o=pgDrop(modOrigin(m));O.set(o,i*3);F[i]=modSf(m);
    if(!(F[i]&1))for(let j=i-1;j>=0;j--)if(O[j*3]===O[i*3]&&O[j*3+1]===O[i*3+1]&&O[j*3+2]===O[i*3+2]){F[i]|=1;break;}});  // duplicate: not linked
  // the map cells (AddNode): every linked node in the four cells round it
  const NC=c=>{let v=c+8192-128;if(v<0)v=c+8192+128-1;return Math.trunc(v)>>8;};
  // (PathSearch::AddToGrid: a cell keeps 128 nodes; one more prints "Node overflow")
  const cellOver=[];
  const cells=new Map(),add=(x,y,i)=>{if(x<0||x>=64||y<0||y>=64)return;const key=x*64+y;let l=cells.get(key);if(!l){l=[];cells.set(key,l);}if(l.length<128)l.push(i);else cellOver.push([x,y,i]);};
  for(let i=0;i<n;i++){if(F[i]&1)continue;const x=NC(O[i*3]),y=NC(O[i*3+1]);add(x,y,i);add(x+1,y,i);add(x,y+1,i);add(x+1,y+1,i);}
  const near=i=>{const gx=gridCoord(O[i*3]),gy=gridCoord(O[i*3+1]),s=new Set();
    for(let x=gx-1;x<=gx+1;x++)for(let y=gy-1;y<=gy+1;y++){const l=cells.get(x*64+y);if(l)for(const j of l)if(j!==i)s.add(j);}return s;};
  // the .pth's links, less those to and from the changed nodes (they are worked out again)
  // A node that already had its 48 paths may have been cut short (more nodes were left to try):
  // with a node near it deleted, moved or added, the game would link it again, so those nodes
  // are linked afresh below. Within 640 units: its cells reach 384 and a changed node's too.
  const base=new Int32Array(n0);for(let k=0;k<B0.c.length;k+=9){const a=B0.c[k]|0;if(a<n0)base[a]++;}
  const chg=[];for(const k of ek)chg.push(B0.o[k*3],B0.o[k*3+1]);for(const[k]of edits)chg.push(O[k*3],O[k*3+1]);
  for(let i=n0;i<n;i++)chg.push(O[i*3],O[i*3+1]);
  const rc=new Set();
  if(chg.length)for(let j=0;j<n0;j++){if(base[j]<48||ek.has(j)||(F[j]&1))continue;
    for(let q=0;q<chg.length;q+=2){const dx=chg[q]-O[j*3],dy=chg[q+1]-O[j*3+1];if(dx*dx+dy*dy<640*640){rc.add(j);break;}}}
  const C=[],kids=new Int32Array(n);
  for(let k=0;k<B0.c.length;k+=9){const a=B0.c[k]|0,b=B0.c[k+1]|0;if(ek.has(a)||ek.has(b)||rc.has(a))continue;
    for(let q=0;q<9;q++)C.push(B0.c[k+q]);kids[a]++;}
  // (PathNode::CheckPathTo: 48 paths a node; one more to check prints "paths per node
  // exceeded" and that node is linked no further)
  const linkOver=new Set();
  const link=(a,b)=>{if(kids[a]>=48){linkOver.add(a);return;}const L=pgLink(P(a),P(b));
    if(L){C.push(a,b,L.fall,L.p1[0],L.p1[1],L.p1[2],L.p2[0],L.p2[1],L.p2[2]);kids[a]++;}};
  // those nodes again, in the game's order: the nodes of the 3x3 cells round each, x then y
  for(const j of rc){const gx=gridCoord(O[j*3]),gy=gridCoord(O[j*3+1]),seen=new Set([j]);
    for(let x=gx-1;x<=gx+1;x++)for(let y=gy-1;y<=gy+1;y++){const l=cells.get(x*64+y);if(!l)continue;
      for(const c of l){if(seen.has(c))continue;seen.add(c);link(j,c);}}}
  const redo=[...ek];for(let i=n0;i<n;i++)redo.push(i);const rs=new Set(redo);
  for(const i of redo){if(F[i]&1)continue;
    for(const j of near(i))link(i,j);                       // the new or changed node to its neighbours
    // and each of the other nodes whose neighbourhood it is in, to it
    for(let j=0;j<n0;j++){if(rs.has(j)||rc.has(j)||F[j]&1)continue;const dx=O[j*3]-O[i*3],dy=O[j*3+1]-O[i*3+1];
      if(dx*dx+dy*dy>=384*384)continue;if(near(j).has(i))link(j,i);}}
  // the links in order of the node they leave (buildRoutes reads them so)
  const idx=[];for(let k=0;k<C.length;k+=9)idx.push(k);
  idx.sort((a,b)=>(C[a]-C[b])||(a-b));
  const C2=new Float32Array(C.length);idx.forEach((k,r)=>{for(let q=0;q<9;q++)C2[r*9+q]=C[k+q];});
  setTimeout(modRender,0);
  return PA_C={n:n,o:O,f:F,c:C2,n0:n0,mod:nodes,edits:new Map(edits),redo:redo,cellOver:cellOver,linkOver:linkOver};
}
// ---- what will go wrong with Modify's nodes in the game --------------------------------
// For the new and changed nodes: 48 paths ("^~^~^ 48 paths per node at (...) exceeded"),
// a full map cell ("^~^~^ PathSearch::AddToGrid: Node overflow at ( x, y )"), no path at
// all (nothing within 384 units it can walk to, or only drops past ai_fallheight), and
// nodes cut off from the map's others: an AI sent from one side to the other gets "^~^~^
// Path not found" (g_patherror 1, on by default). Worked out again when ai_fallheight
// changes, as the game reads it when it draws and walks the paths.
let PA_ISS=null;
function paIssues(){
  const A=PA();if(!A||A.n0==null||!A.redo)return null;
  const fh=CVARS.ai_fallheight;
  if(PA_ISS&&PA_ISS.A===A&&PA_ISS.fh===fh)return PA_ISS;
  const n=A.n,C=A.c,nc=C.length/9,adj=Array.from({length:n},()=>[]),deg=new Int32Array(n),out=new Int32Array(n),high=new Int32Array(n);
  for(let k=0;k<nc;k++){const a=C[k*9]|0,b=C[k*9+1]|0,f=C[k*9+2];out[a]++;
    if(f>fh){high[a]++;continue;}adj[a].push(b);adj[b].push(a);deg[a]++;deg[b]++;}
  // the parts the usable paths join, and whether each has a node of the map's own
  const comp=new Int32Array(n).fill(-1),hasBase=[],csize=[];let nc2=0;
  for(let i=0;i<n;i++){if(comp[i]>=0||(A.f[i]&1))continue;const q=[i];comp[i]=nc2;let b=false,sz=0;
    while(q.length){const v=q.pop();sz++;if(v<A.n0&&!A.edits.has(v))b=true;for(const w of adj[v])if(comp[w]<0){comp[w]=nc2;q.push(w);}}
    hasBase.push(b);csize.push(sz);nc2++;}
  // n counts the problems; info the notes that are only information (lv 0: an own group)
  const R={A:A,fh:fh,node:new Map(),n:0,info:0};
  const note=(i,t)=>{let l=R.node.get(i);if(!l){l=[];R.node.set(i,l);}if(t.lv==null)t.lv=2;l.push(t);if(t.lv)R.n++;else R.info++;};
  const P=i=>fvec([A.o[i*3],A.o[i*3+1],A.o[i*3+2]].map(v=>Math.round(v*100)/100));
  for(const i of A.redo){if(A.f[i]&1)continue;
    if(A.linkOver.has(i))note(i,{k:'links',t:'48 paths: ^~^~^ 48 paths per node at '+P(i)+' exceeded. The game links it no further (and g_nodecheck 1 stops the level: "Node check failed"). Use DONT_LINK on some nodes round it, or fewer nodes here.'});
    if(!deg[i])note(i,{k:'none',t:high[i]?'only drops past ai_fallheight ('+fh+'): no path the AI takes; ai_showroutes draws a red X':'no path: no node within 384 units it can walk to (and none walks to it); ai_showroutes draws a red X'});
    else if(A.n0>0&&!hasBase[comp[i]]){const sz=csize[comp[i]];
      note(i,{k:'island',lv:0,lbl:'own group of '+sz,t:'its own group: '+sz+' node'+(sz===1?'':'s')+' joined to each other but not to the map\'s others. Nothing wrong with that for men who start in here and stay; one sent from here to a spot outside it, or from outside to in here, gets "^~^~^ Path not found" (g_patherror 1). If they must come and go, join it to the rest with a node under 384 units away.'});}
    const w=nodeWall([A.o[i*3],A.o[i*3+1],A.o[i*3+2]]);
    if(w)note(i,{k:'wall',t:nodeWallText(w)});}
  // the links of the map's own nodes the new ones crowd out
  for(const a of A.linkOver)if(a<A.n0&&!A.edits.has(a)&&!(A.f[a]&1))note(a,{k:'links',t:'48 paths: ^~^~^ 48 paths per node at '+P(a)+' exceeded (a node of the map\'s that Modify\'s new ones crowd)'});
  const seen=new Set();
  for(const[x,y,i]of A.cellOver){const key=x*64+y;if(seen.has(key))continue;seen.add(key);
    if(!A.redo.includes(i))continue;
    note(i,{k:'cell',t:'^~^~^ PathSearch::AddToGrid: Node overflow at ( '+x+', '+y+' ): 128 nodes in that 256-unit cell already, so the game leaves this node out of it and nodes there won\'t link to it'});}
  return PA_ISS=R;
}
// a node's issues as one line each, for the cards and the status
function paIssueList(i){const R=paIssues();return(R&&R.node.get(i)||[]).concat(paOverNotes(i));}
// The 48-path limit (PathNode::CheckPathTo): a node keeps at most 48 paths, and when one more
// node is still to be tried the game prints "^~^~^ 48 paths per node at (origin) exceeded" and
// links the node no further. Worked out from the paths in use (the .pth's, or the ones worked
// out here) by going through each full node's candidates in the game's order: the nodes of the
// 3x3 cells round it, x then y, each cell's nodes in order. {over: node -> the first candidate
// left untried, full: nodes with exactly 48}.
let PA_OVER=null;
// a map node Modify deleted (or changed to something that isn't a path node): it is gone, so
// it has no errors of its own
function pnGone(A,i){const m=A&&A.edits?A.edits.get(i):null;return !!m&&(m.del||!modIsNode(m));}
function paOver(){
  const B=PA();if(!B)return{over:new Map(),full:new Set()};
  if(PA_OVER&&PA_OVER.src===B)return PA_OVER;
  const n=B.n,O=B.o,F=B.f,C=B.c,kids=new Int32Array(n),ch=Array.from({length:n},()=>null);
  for(let k=0;k<C.length;k+=9){const a=C[k]|0;if(a<0||a>=n)continue;kids[a]++;(ch[a]||(ch[a]=new Set())).add(C[k+1]|0);}
  const NC=c=>{let v=c+8192-128;if(v<0)v=c+8192+128-1;return Math.trunc(v)>>8;};
  const cells=new Map(),add=(x,y,i)=>{if(x<0||x>=64||y<0||y>=64)return;const k=x*64+y;let l=cells.get(k);if(!l){l=[];cells.set(k,l);}if(l.length<128)l.push(i);};
  for(let i=0;i<n;i++){if(F[i]&1)continue;const x=NC(O[i*3]),y=NC(O[i*3+1]);add(x,y,i);add(x+1,y,i);add(x,y+1,i);add(x+1,y+1,i);}
  const over=new Map(),full=new Set();
  for(let i=0;i<n;i++){
    if(kids[i]<48||(F[i]&1))continue;full.add(i);
    const gx=gridCoord(O[i*3]),gy=gridCoord(O[i*3+1]),seen=new Set([i]);let cnt=0,done=false;
    for(let x=gx-1;x<=gx+1&&!done;x++)for(let y=gy-1;y<=gy+1&&!done;y++){
      if(x<0||x>=64||y<0||y>=64)continue;const l=cells.get(x*64+y);if(!l)continue;
      for(const j of l){if(seen.has(j))continue;seen.add(j);
        if(cnt>=48){over.set(i,j);done=true;break;}
        if(ch[i]&&ch[i].has(j))cnt++;}}
  }
  return PA_OVER={src:B,over:over,full:full};
}
function paOverNotes(i){
  const B=PA();if(!B||i>=B.n||pnGone(B,i))return [];
  const R=PA_ISS&&PA_ISS.A===B?PA_ISS:null;
  if(R&&(R.node.get(i)||[]).some(x=>x.k==='links'))return [];       // Modify's own 48-path note (paIssues) already says it
  const O=paOver();
  const p=fvec([B.o[i*3],B.o[i*3+1],B.o[i*3+2]].map(v=>Math.round(v*100)/100));
  if(O.over.has(i))return [{k:'links',lv:2,t:'48 paths: this node has the 48 the game allows and more nodes were still to be linked, so the game prints "^~^~^ 48 paths per node at '+p+' exceeded" and links it no further. Use DONT_LINK on some nodes round it.'}];
  if(O.full.has(i))return [{k:'links',lv:0,t:'48 paths: exactly the limit, with no node left to try, so the game prints nothing for it. One more node near it would.'}];
  return [];
}
// ---- room for an actor at a path node (not a game check: the game never tests it) -------
// An actor's box is 30 units across and 94 tall (MINS -15 -15 0, MAXS 15 15 94; the path
// links test 31, CheckMove's 15.5). A node nearer a wall than that puts part of a man
// standing on it inside the wall. The game links the node anyway where its own test lets
// it, so the trouble only shows when someone is sent there: he stops against the wall short
// of the node (it may then never count as reached, so a runto there can hang without
// movedone), links out of it can fail in some directions (the red one-way arrowheads), and
// a failsafe noclip can leave him inside the wall. So: the actor's capsule, as the AI's
// movement traces see it, stood on the node's floor point, lifted one step (18) so stairs,
// slopes and kerbs don't count; if it starts inside the map, the nearest spot in eight
// directions out to 32 units where it doesn't. Kept per spot (the map's solids don't move).
const NW_MIN=[-15,-15,0],NW_MAX=[15,15,94-18],NW_LIFT=18,PA_WALL=new Map();
const NW_DIRS=['+X','+X +Y','+Y','-X +Y','-X','-X -Y','-Y','+X -Y'];
function nodeWall(o){
  const key=Math.round(o[0]*4)+','+Math.round(o[1]*4)+','+Math.round(o[2]*4);
  if(PA_WALL.has(key))return PA_WALL.get(key);
  const hit=p=>{const s=[p[0],p[1],p[2]+NW_LIFT],t=pgTrace(s,s,NW_MIN,NW_MAX,true);return !!(t&&t.startsolid);};
  let r=null;
  try{if(hit(o)){r={d:0,k:-1};let found=false;
    for(const d of[4,8,12,16,20,24,32]){if(found)break;
      for(let k=0;k<8;k++){const a=k*Math.PI/4;
        if(!hit([o[0]+Math.cos(a)*d,o[1]+Math.sin(a)*d,o[2]])){r={d:d,k:k};found=true;break;}}}}}
  catch(_e){r=null;}
  PA_WALL.set(key,r);return r;
}
function nodeWallText(w){
  return 'in the wall: a man standing on this node (30 units across, 94 tall) is partly inside the map'+
    (w.d?'; about '+w.d+' units toward '+NW_DIRS[w.k]+' clears it':'; nowhere within 32 units clears it')+
    '. Sent here he stops against the wall short of it (a runto may never report movedone), paths out of it can fail one way, and a failsafe noclip can leave him inside the wall. Keep a node at least 16 units off a wall (a corner or cover node too: the animations lean out from there).';
}
// the yaw of path node i (new nodes: their own angles)
function paYaw(i){const A=PA(),yaw=m=>entAngles(Object.fromEntries(m.kv.map(([k,v])=>[k.toLowerCase(),v])))[1];
  if(A&&A.mod&&i>=A.n0)return yaw(A.mod[i-A.n0]);
  if(A&&A.edits&&A.edits.has(i))return yaw(A.edits.get(i));
  return nodeYaw(i);}

// ---- adding, editing, removing -----------------------------------------------------------
// Add: the next click on the map places one there (as the path editor's Place node did)
function modAdd(cls){
  if(MOD.placing&&MOD.placing.move==null&&MOD.placing.cls===cls){modPlaceCancel();return;}
  if(!modLimitCheck(cls))return;
  if(MOD.edit>=0)modEditClose(true);
  if(MOD.trim)modTrim(false);
  MOD.placing={cls:cls};MOD.ghost=null;modRender();
  flash('Click anywhere on the map to place the '+cls+' (Esc cancels)');
}
function modPlaceCancel(){if(!MOD.placing)return;const P=MOD.placing,mv=P.move!=null;MOD.placing=null;MOD.ghost=null;
  // a Copy not put down: the copies go again, as if it never happened
  if(P.copy&&MOD.undo.length){modRestore(MOD.undo.pop());modChanged(true);flash('Not copied');return;}
  if(mv)paDirty();modRender();requestDraw();flash(mv?'Not moved':'Not placed');}
// Move (and Copy): the selected entities follow the mouse together, each kept where it is
// from the first (the one placed under the cursor)
function modGroupStart(lead,others,copy){
  const a=modOrigin(lead);
  MOD.placing={cls:modCls(lead)||'info_null',move:MOD.ents.indexOf(lead),group:others,
    offs:others.map(m=>{const o=modOrigin(m);return[o[0]-a[0],o[1]-a[1],o[2]-a[2]];}),copy:!!copy};
  MOD.ghost=null;paDirty();modRender();
}
// Move: the selected new entity follows the mouse again until a click puts it down
function modMove(){
  if(MOD.placing&&MOD.placing.move!=null){modPlaceCancel();return;}
  if(MOD.trim)return;
  if(MOD.edit>=0)modEditClose(true);
  const L=modSelEnts(true),m=L[0];if(!m)return;
  MOD.sel=MOD.ents.indexOf(m);for(const x of L.slice(1))MOD.multi.add(x);
  modGroupStart(m,L.slice(1),false);
  flash('Move: click anywhere on the map to put the '+(L.length>1?L.length+' selected (as they are spaced now)':modCls(m))+' there (Esc or Move again cancels)');
}
// where a click at hit h puts a new entity of class cls: a path node 16 units over the
// spot (the game drops it to the floor from 36 up), anything else with its box's bottom on it
function modPlaceAt(h,cls){
  if(!h||!h.point)return null;
  const src=MOD.placing&&MOD.placing.move!=null?MOD.ents[MOD.placing.move]:null;
  const m=src||{kv:[['classname',cls]]},p=h.point;
  const up=cls==='info_pathnode'?16:Math.max(0,-modBox(m).mins[2]);
  if(!GRID.on)return[Math.round(p[0]),Math.round(p[1]),Math.round(p[2]+up)];
  // the grid on: its nearest corner, never with the box down in the floor
  const o=[gridSnap(p[0]),gridSnap(p[1]),gridSnap(p[2]+up)],lo=p[2]+Math.max(0,-modBox(m).mins[2]);
  if(o[2]<lo-0.01)o[2]+=gridSize();
  return o;
}
// whether a class faces a way: most of the map's own of that class have an angle, or (none
// in the map) a player start, an actor, a turret or a vehicle
function modFaces(cls){
  let n=0,a=0;for(const e of MAP.ents)if(e.cls===cls){n++;if(e.kvl.angle!=null||e.kvl.angles!=null)a++;}
  if(n)return a*2>=n;
  return /^(info_player|ai_|actor|turret|vehicle|script_vehicle)|turret/.test(cls);
}
function modPlaceClick(x,y){
  const P=MOD.placing;if(!P)return false;
  const o=modPlaceAt(hitInfo(pickAt(x,y),x,y),P.cls);
  if(!o){flash('Nothing under the cursor there: click on the map (Esc cancels)');return true;}
  if(P.move!=null){const m=MOD.ents[P.move];MOD.placing=null;MOD.ghost=null;
    if(!P.copy)modHist();                       // (a Copy's step was kept when it was made)
    if(m){modSetKv(m,'origin',o.join(' '));MOD.sel=P.move;
      (P.group||[]).forEach((g,k)=>{const d=P.offs[k];modSetKv(g,'origin',[o[0]+d[0],o[1]+d[1],o[2]+d[2]].map(v=>+v.toFixed(3)).join(' '));});}
    const n=1+(P.group?P.group.length:0);
    modChanged(true);modPlacedSel();flash((P.copy?'Copied ':'Moved ')+(n>1?n+' ':'')+'to ( '+o.join(' ')+' )');return true;}
  if(!modLimitCheck(P.cls)){modPlaceCancel();return true;}
  modHist();
  const m={id:MOD.nid++,kv:[['classname',P.cls],['origin',o.join(' ')]]};
  // a class that faces somewhere gets an "angle": the way the camera looks, to 45 degrees
  if(modFaces(P.cls))m.kv.push(['angle',String(((Math.round(cam.yaw/45)*45)%360+360)%360)]);
  MOD.ents.push(m);MOD.sel=MOD.ents.length-1;MOD.placing=null;MOD.ghost=null;
  modChanged(true);modPlacedSel();flash('Placed '+P.cls+' at ( '+o.join(' ')+' ): Edit parameters, Move or Trim origin to adjust it');
  return true;
}
// The one just put down is the selection: a new one (added or a copy) lets go of the map's
// selected brushes and entities, as a click on it does, and More info (N), when open,
// turns to it, so Edit parameters there edits it and not what was selected before.
function modPlacedSel(){
  const m=MOD.ents[MOD.sel];if(!m)return;
  if(!modIsMap(m)&&SEL.size){SEL.clear();lastHit=null;selectionChanged();}
  if($('info').classList.contains('on')&&infoMode==='sel')showInfo('sel');
  modRender();requestDraw();
}
// while placing: where it would go under the cursor (the hover read-out finds it)
function modGhost(h){
  if(!MOD.placing)return;
  const o=modPlaceAt(h,MOD.placing.cls),k=o?o.join(','):'',was=MOD.ghost?MOD.ghost.join(','):'';
  MOD.ghost=o;if(k!==was)requestDraw();
}
function modRemove(i){
  if(i<0||i>=MOD.ents.length)return;
  if(MOD.edit===i)modEditClose(false);
  if(MOD.trim&&modIsSel(i))modTrim(false);
  if(MOD.placing&&MOD.placing.move!=null)modPlaceCancel();
  if(!MOD.ents[i])return;
  modHist();
  // a map entity is flagged DEL (left out of the saved map); on a DEL or changed one the
  // button is Restore, which puts back the map's keys and un-flags it
  const m=MOD.ents[i];MOD.multi.delete(m);
  if(modIsMap(m)){
    if(m.del||modKvEdited(m)){m.del=false;m.kv=m.orig.map(x=>x.slice());modChanged(true);flash(entName(m.ei)+' is as the map has it again');return;}
    m.del=true;MOD.sel=-1;if(SEL.has('e'+m.ei)){SEL.delete('e'+m.ei);selectionChanged();}
    modChanged(true);flash('DEL: '+entName(m.ei)+' is left out of the saved map (Restore or Undo, Alt+Z, puts it back; not saved yet)');return;}
  MOD.ents.splice(i,1);
  if(MOD.edit>i)MOD.edit--;
  MOD.sel=Math.min(MOD.sel,MOD.ents.length-1);
  modChanged(true);
}
// Delete (Restore) for everything selected: new ones removed, the map's own put back
function modRemoveSel(){
  const L=modSelEnts(false);if(!L.length)return;
  if(L.length===1){modRemove(MOD.ents.indexOf(L[0]));return;}
  if(MOD.edit>=0)modEditClose(false);
  if(MOD.trim)modTrim(false);
  if(MOD.placing)modPlaceCancel();
  modHist();let nd=0,nr=0;
  for(const m of L){if(modIsMap(m)){if(m.del||modKvEdited(m)){m.del=false;m.kv=m.orig.map(x=>x.slice());nr++;}else{m.del=true;nd++;SEL.delete('e'+m.ei);}}
    else{const k=MOD.ents.indexOf(m);if(k>=0){MOD.ents.splice(k,1);nd++;}}}
  MOD.sel=-1;MOD.multi.clear();selectionChanged();modChanged(true);
  flash((nd?'Deleted '+nd:'')+(nd&&nr?', ':'')+(nr?'restored '+nr+' of the map\'s own':'')+' (Undo, Alt+Z, puts them back)');
}
// Copy: the selected entities again (no targetname or target, so nothing is named twice),
// following the mouse together as Move does until a click puts them down; Esc takes them away
function modCopySel(){
  if(MOD.placing&&MOD.placing.copy){modPlaceCancel();return;}
  if(MOD.edit>=0)modEditClose(true);
  if(MOD.trim)modTrim(false);
  if(MOD.placing)modPlaceCancel();
  if(MOD.linking)modLinkCancel();
  const L=modSelEnts(true);if(!L.length){flash('Select what to copy first (Shift+click adds more)');return;}
  modHist();
  const copies=[];let dropped=false;
  for(const m of L){if(!modLimitCheck(modCls(m))){modRestore(MOD.undo.pop());modChanged(true);return;}
    const kv=m.kv.filter(x=>{const k=x[0].toLowerCase();if(k==='targetname'||k==='target'){dropped=true;return false;}return true;}).map(x=>x.slice());
    const c={id:MOD.nid++,kv:kv};MOD.ents.push(c);copies.push(c);}
  MOD.sel=MOD.ents.indexOf(copies[0]);MOD.multi=new Set(copies.slice(1));
  // the copies are the selection now: the map's lets go
  if(SEL.size){SEL.clear();lastHit=null;selectionChanged();}
  modGroupStart(MOD.ents[MOD.sel],copies.slice(1),true);
  flash('Copied '+(copies.length>1?copies.length+' (as they are spaced)':modName(copies[0]))+': click on the map to put '+(copies.length>1?'them':'it')+' down (Esc takes '+(copies.length>1?'them':'it')+' away)'+(dropped?'. Their targetname and target were left out':''));
}
// after any change: the list, the drawing, and the paths when nodes changed
function modChanged(paths){if(paths)paDirty();modHideSync();modRender();requestDraw();modBackupSoon();}
// ---- Modify's work kept safe ----------------------------------------------------------------
// Unsaved work is copied, a moment after each change, to the launcher (a file in the
// output folder's modify_recovery, per map and map_time; mohaa-modify-backup) or, in a
// browser, to its local storage. When this map opens again with such a copy, the page
// offers it back. A save, or Discard changes, clears it. A reload of the page, or leaving
// it, while work is unsaved asks first (beforeunload).
let _modBkT=0,_modBkKey=null;
function modBackupId(){return{map:String(D.name||''),path:String(D.path||''),mt:String((MAP.ents[0]&&MAP.ents[0].kvl.map_time)||'')};}
function modBackupSoon(){if(_modBkT)clearTimeout(_modBkT);_modBkT=setTimeout(modBackupNow,1200);}
function modBackupNow(){
  _modBkT=0;if(!MAP||!MOD)return;
  const un=modUnsaved(),id=modBackupId();
  const snap=un?modSnap():null,key=snap?JSON.stringify(snap.ents):'';
  if(key===_modBkKey)return;_modBkKey=key;
  // (the entities are stringified once, for the change check above, and reused in the file's text)
  const txt=snap?JSON.stringify(Object.assign(id,{t:Date.now(),nw:un.nw,ch:un.ch})).slice(0,-1)+',"ents":'+key+'}':JSON.stringify(id);
  if(txt.length>8e6)return;
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-modify-backup\n'+txt);return;}}catch(_e){}
  const k='mohaaMapViewerModify|'+id.map+'|'+id.mt;
  if(snap)LS.set(k,txt);else{try{localStorage.removeItem(k);}catch(_e){}}
}
// a copy found when the map opens: offer it back
function modRecoverAsk(){
  const id=modBackupId();
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-modify-recovery\n'+JSON.stringify(id));return;}}catch(_e){}
  let b=null;try{b=JSON.parse(LS.get('mohaaMapViewerModify|'+id.map+'|'+id.mt)||'null');}catch(_e){}
  if(b)window.MOHAA_MODIFY_RECOVERY(b);
}
window.MOHAA_MODIFY_RECOVERY=function(b){
  if(!b||!Array.isArray(b.ents)||!b.ents.length||MOD.ents.some(m=>!modIsMap(m)||modEdited(m)))return;
  const id=modBackupId();if(b.map!==id.map||String(b.mt||'')!==id.mt)return;
  const ents=b.ents.filter(e=>e&&Array.isArray(e.kv)&&e.kv.every(x=>Array.isArray(x)&&x.length===2)&&
    (e.ei==null||(e.ei>0&&e.ei<MAP.ents.length&&Array.isArray(e.orig))));
  if(!ents.length)return;
  const nw=ents.filter(e=>e.ei==null).length,ch=ents.length-nw,when=b.t?new Date(b.t).toLocaleString():'earlier';
  const ov=document.createElement('div');ov.className='ov';ov.id='modRecOv';
  ov.innerHTML='<div class="card" style="max-width:520px"><h3>Unsaved Modify work</h3><div class="co" style="margin-bottom:10px">'+
    'This map was closed or reloaded with Modify\'s work not saved ('+when+'): '+(nw?nw+' new entit'+(nw===1?'y':'ies'):'')+(nw&&ch?' and ':'')+
    (ch?ch+' changed map entit'+(ch===1?'y':'ies'):'')+'. Restore it?</div><div class="row">'+
    '<button id="bRecYes">Restore</button><span style="flex:1"></span><button id="bRecNo">Discard</button></div></div>';
  $('stage').appendChild(ov);
  const close=()=>ov.remove();
  $('bRecYes').onclick=()=>{close();
    modHist();
    modRestore({ents:ents.map(e=>({id:MOD.nid++,ei:e.ei==null?undefined:e.ei,kv:e.kv.map(x=>[String(x[0]),String(x[1])]),
      orig:e.ei!=null?MAP.ents[e.ei].kv.map(x=>[x[0],x[1]]):null,hid:!!e.hid,del:!!e.del&&e.ei!=null})),sel:null,multi:[]});
    MOD.ents.forEach(m=>{if(m.ei===undefined)delete m.ei;});
    modChanged(true);lineDirty=true;flash('Restored Modify\'s unsaved work: '+nw+' new, '+ch+' changed');};
  $('bRecNo').onclick=()=>{close();_modBkKey=null;modBackupNow();flash('Unsaved Modify work discarded');};
};
window.addEventListener('beforeunload',e=>{
  if(MOD&&!MOD.leaving&&typeof modUnsaved==='function'&&MAP&&modUnsaved()){modBackupNow();e.preventDefault();e.returnValue='';}});
function modDeselect(){const m=MOD.ents[MOD.sel];
  if(MOD.trim)modTrim(false);
  if(MOD.placing&&MOD.placing.move!=null)modPlaceCancel();
  MOD.sel=-1;MOD.multi.clear();
  if(m&&modIsMap(m)&&SEL.has('e'+m.ei)){SEL.delete('e'+m.ei);selectionChanged();}
  if($('info').classList.contains('on')&&infoMode==='sel')showInfo('sel');
  modRender();requestDraw();}
function modToggleHide(i){const m=MOD.ents[i];if(!m)return;
  if(!m.hid&&(MOD.edit===i||(MOD.trim&&MOD.sel===i)||(MOD.placing&&MOD.placing.move===i))){flash('Finish editing it first');return;}
  HIDE_UNDO.push({mod:m,was:!!m.hid,e:[],p:[]});if(HIDE_UNDO.length>500)HIDE_UNDO.shift();     // Ctrl+Z puts it back
  m.hid=!m.hid;modChanged(false);flash((m.hid?'Hidden: ':'Shown again: ')+modName(m)+(m.hid?' (Shift+click its square to show it)':''));}
// a row picked: an entry for a map entity selects that entity in the map as well
function modSelect(i){MOD.sel=i;MOD.multi.clear();const m=MOD.ents[i];
  if(m&&modIsMap(m)&&!(SEL.size===1&&SEL.has('e'+m.ei))){SEL.clear();SEL.add('e'+m.ei);lastHit={ent:m.ei,face:-1,prim:-1,point:null};selectionChanged();}
  if(m&&!modIsMap(m)&&$('info').classList.contains('on')&&infoMode==='sel')showInfo('sel');
  modHideSync();modRender();requestDraw();}
// "To view": where the middle of the screen meets the map (a node goes on the floor there)
// Fly to: the camera to the entity, a little away from it (the button, a click on its
// selected row in the list)
function modFly(){const m=MOD.ents[MOD.sel];if(!m)return;flyTo(lookFrom(modOrigin(m),220),null,null);requestDraw();}

// ---- Edit parameters: the entity as the .bsp's entity lump has it --------------------------
// One entity as "key" "value" lines. A quoted key or value ends on its own line (the
// game's parser would read a quote left open on into the next lines and take the rest of
// the entity, braces and all, as keys and values), and holds no { or }.
function modParse(txt){
  const re=/"([^"]*)"|(\/\/.*$)|([{}])|(\S+)/g,kv=[];let opened=false,closed=false,key=null,keyLn=0;
  const lines=String(txt).split(/\r?\n/);
  for(let n=0;n<lines.length&&!closed;n++){
    const ln=lines[n],L=n+1;
    const q=(ln.replace(/"[^"]*"|\/\/.*$/g,m=>m[0]==='"'?m:'').match(/"/g)||[]).length;   // a // inside quotes is not a comment
    if(q%2)throw new Error('line '+L+': a quote isn\'t closed on its line');
    let r;re.lastIndex=0;
    while((r=re.exec(ln))){
      if(r[2]!=null)break;
      if(r[3]!=null){
        if(r[3]==='{'){if(opened||kv.length||key!=null)throw new Error('line '+L+': a "{" inside the entity');opened=true;continue;}
        closed=true;break;}
      const t=r[1]!=null?r[1]:r[4];
      if(/[{}]/.test(t))throw new Error('line '+L+': a { or } inside a key or value');
      if(key==null){if(!t)throw new Error('line '+L+': an empty key');key=t;keyLn=L;}
      else{kv.push([key,t]);key=null;}
    }
    if(key!=null&&keyLn===L)throw new Error('line '+L+': "'+key+'" has no value on its line');
  }
  if(!kv.some(x=>x[0].toLowerCase()==='classname'&&x[1]))throw new Error('no "classname"');
  if(kv.some(x=>x[0].toLowerCase()==='origin')&&!parseVec(kv.find(x=>x[0].toLowerCase()==='origin')[1],3))throw new Error('"origin" needs three numbers');
  return kv;
}
let _modT=0;
function modEditOpen(i){
  if(i<0||i>=MOD.ents.length)return;
  if(MOD.placing)modPlaceCancel();
  if(MOD.trim)modTrim(false);
  MOD.edit=i;MOD.sel=i;MOD.editKv=MOD.ents[i].kv.map(x=>x.slice());MOD.editSnap=modSnap();
  MOD.hist=[modText(MOD.ents[i])];MOD.hpos=0;
  $('modEdT').textContent='Edit parameters: '+modName(MOD.ents[i]);
  $('modTxt').value=modText(MOD.ents[i]);$('modErr').textContent='';
  $('modEd').classList.add('on');modEdPlace();modHistBtns();paDirty();modRender();
  setTimeout(()=>$('modTxt').focus(),0);
}
function modEditApply(){
  const m=MOD.ents[MOD.edit];if(!m)return;
  try{m.kv=modParse($('modTxt').value);$('modErr').textContent='';$('modEdT').textContent='Edit parameters: '+modName(m);modRender();requestDraw();}
  catch(err){$('modErr').textContent=err.message;}
}
// each pause in typing is one step of Undo / Redo (from when the box opened)
function modHistPush(){const t=$('modTxt').value;if(t===MOD.hist[MOD.hpos])return;
  MOD.hist.length=MOD.hpos+1;MOD.hist.push(t);MOD.hpos++;modHistBtns();}
function modHistGo(d){
  clearTimeout(_modT);modHistPush();
  const n=MOD.hpos+d;if(n<0||n>=MOD.hist.length)return;
  MOD.hpos=n;$('modTxt').value=MOD.hist[n];modEditApply();modHistBtns();
}
function modHistBtns(){const b=MOD.hist||[];$('bModUndo').disabled=!(MOD.hpos>0);$('bModRedo').disabled=!(MOD.hpos<b.length-1);}
function modEditInput(){
  clearTimeout(_modT);
  _modT=setTimeout(()=>{modEditApply();modHistPush();},180);
  $('bModUndo').disabled=false;$('bModRedo').disabled=true;    // a change typed: there is one to undo
}
// Done keeps what is typed (if it reads; keep=false puts back what it was); either way the
// entity is placed again and its paths worked out
function modEditClose(keep){
  const i=MOD.edit;if(i<0)return;
  const m=MOD.ents[i];
  if(m){if(keep){try{m.kv=modParse($('modTxt').value);}catch(err){$('modErr').textContent=err.message;return;}
      if(MOD.editSnap&&JSON.stringify(m.kv)!==JSON.stringify(MOD.editKv))modHist(MOD.editSnap);}
    else m.kv=MOD.editKv;}
  MOD.editSnap=null;
  MOD.edit=-1;$('modEd').classList.remove('on');
  if(document.activeElement===$('modTxt'))$('modTxt').blur();
  modChanged(true);
}

// ---- Trim origin: the arrow keys / WASD move the entity, the camera stays ----------------
function modTrim(on){
  if(on==null)on=!MOD.trim;
  if(on&&MOD.edit>=0)modEditClose(true);
  if(on&&MOD.placing)modPlaceCancel();
  if(on){const L=modSelEnts(true);if(!L.length){flash('Select an entity first');return;}
    MOD.sel=MOD.ents.indexOf(L[0]);for(const x of L.slice(1))MOD.multi.add(x);
    MOD.trimSnap=modSnap();MOD.trimHist=false;}
  if(on&&MOD.placing&&MOD.placing.move!=null)return;
  MOD.trim=on;if(on){stopCamera();}
  paDirty();modRender();
  flash(on?'Trim origin: W A S D / arrows move it, Space / C up and down, Esc or T stops':'Trim origin off');
}
// the world axis nearest the way the camera faces (forward) and its right
function modAxes(){const y=((cam.yaw%360)+360)%360,q=Math.round(y/90)%4;
  const f=[[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]][q];return{f:f,r:[f[1],-f[0],0]};}
function modTrimKey(e){
  const kl=e.key.toLowerCase(),A=modAxes(),st=MOD_STEPS[MOD.stepI];
  let d=null,dir='';
  if(kl==='w'||kl==='arrowup'){d=A.f;dir='f';}else if(kl==='s'||kl==='arrowdown'){d=A.f.map(v=>-v);dir='b';}
  else if(kl==='d'||kl==='arrowright'){d=A.r;dir='r';}else if(kl==='a'||kl==='arrowleft'){d=A.r.map(v=>-v);dir='l';}
  else if(kl===' '){d=[0,0,1];dir='u';}else if(kl==='c'){d=[0,0,-1];dir='d';}
  else if(kl==='escape'||kl==='t'){modTrim(false);return true;}
  if(!d)return CAM_KEYS_FREE.has(kl)||CAM_KEYS_RAD.has(kl);   // the camera stays put
  const L=modSelEnts(false);if(!L.length){modTrim(false);return true;}
  if(!MOD.trimHist){modHist(MOD.trimSnap);MOD.trimHist=true;}     // one step for the whole trim
  for(const m of L){const o=modOrigin(m);modSetKv(m,'origin',[o[0]+d[0]*st,o[1]+d[1]*st,o[2]+d[2]*st].map(v=>+v.toFixed(3)).join(' '));}
  MOD.flash[dir]=performance.now();setTimeout(requestDraw,230);
  modRender();requestDraw();return true;
}

// ---- the volumes of the level script's triggers (Script trigs) ---------------------------
// Each trigger the .scr spawns with a setsize, as a see-through box in the common/trigger
// green with its edges, the way the map's own trigger brushes look; tinted with the
// selection's colour while it is selected. Drawn with Modify's line program, behind the map's
// surfaces like them; pickScriptTrigs makes their sides clickable.
let SCRTRIGS=null;
function drawScriptTrigs(vp){
  if(!gl||(hiddenMask&C_SCRTRIG))return;
  if(!SCRTRIGS)SCRTRIGS=ENTS.filter(X=>X.scrTrig);
  if(!SCRTRIGS.length)return;
  const T=[],L=[],selE=selectedEnts(),G=[0.35,0.85,0.35];
  const E=[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]];
  for(const X of SCRTRIGS){
    if(hidEnt.has(X.ei)||!X.box)continue;
    // selected: tinted with the selection's colour, as a selected trigger brush is
    const P=boxCorners(X.box),sel=selE.has(X.ei),C=sel?hexRGB(TH.sel):G,fc=[C[0],C[1],C[2],sel?0.38:0.18],lc=[C[0],C[1],C[2],sel?1:0.8];
    for(const q of[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]])
      for(const k of[q[0],q[1],q[2],q[0],q[2],q[3]]){const p=P[k];T.push(p[0],p[1],p[2],p[0],p[1],p[2],fc[0],fc[1],fc[2],fc[3]);}
    for(const[a,d]of E){const p=P[a],q=P[d];
      L.push(p[0],p[1],p[2],q[0],q[1],q[2],lc[0],lc[1],lc[2],lc[3],q[0],q[1],q[2],p[0],p[1],p[2],lc[0],lc[1],lc[2],lc[3]);}}
  if(!T.length)return;
  if(!PMODT)PMODT=compile(VS_GVL,FS_LINE);
  if(!B.strBuf){B.strBuf=gl.createBuffer();B.vStr=gvLineVAO(B.strBuf,true);gl.bindVertexArray(null);}
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);gl.disable(gl.CULL_FACE);
  gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  gvUniforms(PMODT,vp,0.0015);
  gl.bindVertexArray(B.vStr);gl.bindBuffer(gl.ARRAY_BUFFER,B.strBuf);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(T),gl.STREAM_DRAW);gl.drawArrays(gl.TRIANGLES,0,T.length/10);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(L),gl.STREAM_DRAW);gl.drawArrays(gl.LINES,0,L.length/10);
  gl.bindVertexArray(null);gl.disable(gl.BLEND);gl.depthMask(true);
}
// The same boxes in the pick pass: a click on one's side selects the trigger, as a click on
// a trigger brush does (its pick id is the entity's, as a marker's)
function pickScriptTrigs(vp){
  if(!gl||(hiddenMask&C_SCRTRIG))return;
  if(!SCRTRIGS)SCRTRIGS=ENTS.filter(X=>X.scrTrig);
  if(!SCRTRIGS.length)return;
  const P=[],K=[];
  for(const X of SCRTRIGS){
    if(hidEnt.has(X.ei)||!X.box)continue;
    const C=boxCorners(X.box),id=NF+1+X.ei;
    for(const q of[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]])
      for(const k of[q[0],q[1],q[2],q[0],q[2],q[3]]){const p=C[k];P.push(p[0],p[1],p[2]);K.push(id);}}
  if(!P.length)return;
  if(!B.stPick){B.stPick=gl.createBuffer();B.stPickK=gl.createBuffer();B.vStPick=gl.createVertexArray();gl.bindVertexArray(B.vStPick);
    attr(0,B.stPick,3);attr(2,B.stPickK,1);gl.disableVertexAttribArray(7);gl.bindVertexArray(null);}
  gl.bindBuffer(gl.ARRAY_BUFFER,B.stPick);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(P),gl.STREAM_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,B.stPickK);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(K),gl.STREAM_DRAW);
  setCommon(PC,vp,1);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
  gl.bindVertexArray(B.vStPick);gl.vertexAttrib4f(7,1,1,1,1);gl.drawArrays(gl.TRIANGLES,0,P.length/3);gl.bindVertexArray(null);
}
// ---- drawing: see-through boxes, their edges, facing and the trim arrows -------------------
let PMODT=null,PMODM=null;
// The entities Modify draws: as the map's markers (VS_MARK / FS_MARK, its shading and its
// bold spawnflags outline), but see-through until saved; then their lines (selection box,
// facing, target, trim arrows) and the outline of one being placed.
function drawModify(vp){
  if((!MOD.ents.length&&!MOD.ghost)||!gl)return;
  const T=[],L=[],M=[];
  const tri=(a,b,c,col)=>{for(const p of[a,b,c])T.push(p[0],p[1],p[2],p[0],p[1],p[2],col[0],col[1],col[2],col[3]);};
  const lin=(p,q,c)=>{L.push(p[0],p[1],p[2],q[0],q[1],q[2],c[0],c[1],c[2],c[3],q[0],q[1],q[2],p[0],p[1],p[2],c[0],c[1],c[2],c[3]);};
  const E=[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]];
  const now=performance.now();let busyA=null;
  // six faces, wound clockwise seen from outside, as initMarkers: bottom, top, -y, +y, -x, +x
  const mark=(mn,mx,c,mk,ol)=>{const F=[[3,2,0,1],[6,7,5,4],[0,4,5,1],[7,6,2,3],[6,4,0,2],[5,7,3,1]],ax=[2,2,1,1,0,0];
    const Cn=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]],O=ol?[ol[0],ol[1],ol[2],1]:[0,0,0,0];
    for(let f=0;f<6;f++){const q=F[f],U=k=>{const u=[k&1?1:0,k&2?1:0,k&4?1:0];u[ax[f]]=0.5;return u;};
      for(const k of[q[0],q[1],q[2],q[0],q[2],q[3]]){const p=Cn(k),u=U(k);M.push(p[0],p[1],p[2],c[0],c[1],c[2],mk,u[0],u[1],u[2],O[0],O[1],O[2],O[3]);}}};
  const Mb=[],Mn=[];       // still / being edited (fainter)
  MOD.ents.forEach((m,i)=>{
    if(!modDrawn(i))return;
    const o=modOrigin(m),b=modBox(m),X=modLook(m),c=X.mcol||X.col,sel=modIsSel(i),busy=modBusy(i);
    const mn=[o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]],mx=[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]];
    const hasM=modHasModel(m);
    if(!hasM){const st=M.length;mark(mn,mx,c,X.mk==null?1:X.mk,X.ol);(busy?Mb:Mn).push([st,M.length]);}
    const P=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]];
    if(!X.ol||hasM)for(const[a,d]of E)lin(P(a),P(d),[c[0]*0.6,c[1]*0.6,c[2]*0.6,0.8]);
    if(sel){const g=2,Q=k=>[(k&1)?mx[0]+g:mn[0]-g,(k&2)?mx[1]+g:mn[1]-g,(k&4)?mx[2]+g:mn[2]-g];for(const[a,d]of E)lin(Q(a),Q(d),[1,1,0.35,1]);}
    // a modelled entity: thin white axes at its origin, turned with its angles (as the
    // original's are), so the new origin can be seen exactly
    if(hasM){const kv2=modKvl(m),ax=anglesAxis(entAngles(kv2)),w=[1,1,1,1];
      for(const k of[0,1,2]){const d=ax[k];lin([o[0]-d[0]*10,o[1]-d[1]*10,o[2]-d[2]*10],[o[0]+d[0]*10,o[1]+d[1]*10,o[2]+d[2]*10],w);}}
    // (its facing arrow and target links are drawn with the map's: rebuildLines)
    if(sel&&MOD.trim){
      // the trim arrows: white, red while it moves that way
      const A=modAxes(),r=Math.max(b.maxs[0]-b.mins[0],b.maxs[1]-b.mins[1])/2+10,cz=(mn[2]+mx[2])/2;
      const dirs={f:A.f,b:A.f.map(v=>-v),r:A.r,l:A.r.map(v=>-v)};
      for(const k in dirs){const d=dirs[k],col=now-(MOD.flash[k]||0)<220?[1,0.15,0.1,1]:[1,1,1,1];
        const s=[o[0]+d[0]*r,o[1]+d[1]*r,cz],e=[s[0]+d[0]*18,s[1]+d[1]*18,cz],sd=[-d[1],d[0],0];
        lin(s,e,col);lin(e,[e[0]-d[0]*7+sd[0]*5,e[1]-d[1]*7+sd[1]*5,cz],col);lin(e,[e[0]-d[0]*7-sd[0]*5,e[1]-d[1]*7-sd[1]*5,cz],col);}
      for(const[k,sg]of[['u',1],['d',-1]]){const col=now-(MOD.flash[k]||0)<220?[1,0.15,0.1,1]:[1,1,1,1];
        const s=[o[0],o[1],sg>0?mx[2]+6:mn[2]-6],e=[s[0],s[1],s[2]+sg*18];
        lin(s,e,col);lin(e,[e[0]+5,e[1],e[2]-sg*7],col);lin(e,[e[0]-5,e[1],e[2]-sg*7],col);}
    }
  });
  // the one being placed, under the cursor
  if(MOD.placing&&MOD.ghost){const G0=MOD.ghost,P0=MOD.placing,lead=P0.move!=null?MOD.ents[P0.move]:null;
    const list=[[lead,G0]];if(P0.group)P0.group.forEach((m,k)=>{const d=P0.offs[k];list.push([m,[G0[0]+d[0],G0[1]+d[1],G0[2]+d[2]]]);});
    for(const[src,g]of list){
    const gm={kv:(src?src.kv.filter(x=>x[0].toLowerCase()!=='origin'):[['classname',MOD.placing.cls]]).concat([['origin',g.join(' ')]])},b=modBox(gm),c=modColour(gm);
    const mn=[g[0]+b.mins[0],g[1]+b.mins[1],g[2]+b.mins[2]],mx=[g[0]+b.maxs[0],g[1]+b.maxs[1],g[2]+b.maxs[2]];
    const P=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]],fc=[c[0],c[1],c[2],0.18];
    for(const q of[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]){tri(P(q[0]),P(q[1]),P(q[2]),fc);tri(P(q[0]),P(q[2]),P(q[3]),fc);}
    for(const[a,d]of E)lin(P(a),P(d),[1,1,1,0.85]);
    lin([g[0],g[1],mn[2]-24],[g[0],g[1],mx[2]+24],[1,1,1,0.6]);}}
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(false);
  gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  if(M.length){
    if(!PMODM)PMODM=compile(VS_MARK,FS_MARK.replace('uniform float uOlW;','uniform float uOlW; uniform float uAlpha;').replace('o=vec4(c,1.0);','o=vec4(c,uAlpha);'));
    if(!B.modMBuf){B.modMBuf=gl.createBuffer();B.vModM=gl.createVertexArray();gl.bindVertexArray(B.vModM);
      attr(0,B.modMBuf,3,56,0);attr(7,B.modMBuf,4,56,12);attr(8,B.modMBuf,3,56,28);attr(10,B.modMBuf,4,56,40);
      gl.disableVertexAttribArray(2);gl.vertexAttrib1f(2,0);gl.bindVertexArray(null);}
    setCommon(PMODM,vp,0);gl.uniform1f(PMODM.u.uOlW,3*DPR);
    gl.enable(gl.CULL_FACE);gl.bindVertexArray(B.vModM);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.modMBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(M),gl.STREAM_DRAW);
    for(const[list,al]of[[Mn,0.5],[Mb,0.35]]){gl.uniform1f(PMODM.u.uAlpha,al);
      for(const[a,z]of list)gl.drawArrays(gl.TRIANGLES,a/14,(z-a)/14);}
    gl.bindVertexArray(null);}
  gl.disable(gl.CULL_FACE);
  if(T.length||L.length){
    if(!PMODT)PMODT=compile(VS_GVL,FS_LINE);
    if(!B.modBuf){B.modBuf=gl.createBuffer();B.vMod=gvLineVAO(B.modBuf,true);gl.bindVertexArray(null);}
    gvUniforms(PMODT,vp,0.0015);
    gl.bindVertexArray(B.vMod);
    gl.bindBuffer(gl.ARRAY_BUFFER,B.modBuf);
    if(T.length){gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(T),gl.STREAM_DRAW);gl.drawArrays(gl.TRIANGLES,0,T.length/10);}
    if(L.length){gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(L),gl.STREAM_DRAW);gl.drawArrays(gl.LINES,0,L.length/10);}
    gl.bindVertexArray(null);}
  gl.disable(gl.BLEND);gl.depthMask(true);
}
// a click in the 3D view on a new entity (nearer than what the map has under the cursor)
function modPick(x,y){
  if(!MOD.ents.length)return -1;
  const d=screenRay(x,y),e=cam.pos;let best=Infinity,bi=-1;
  MOD.ents.forEach((m,i)=>{if(!modDrawn(i))return;const o=modOrigin(m),b=modBox(m);let t0=0,t1=Infinity;
    for(let k=0;k<3;k++){const lo=o[k]+b.mins[k]-2,hi=o[k]+b.maxs[k]+2;
      if(Math.abs(d[k])<1e-9){if(e[k]<lo||e[k]>hi){t0=Infinity;break;}continue;}
      let a=(lo-e[k])/d[k],c=(hi-e[k])/d[k];if(a>c)[a,c]=[c,a];t0=Math.max(t0,a);t1=Math.min(t1,c);}
    if(t0<=t1&&t0<best){best=t0;bi=i;}});
  if(bi<0)return -1;
  const h=hitInfo(pickAt(x,y),x,y);
  if(h&&h.point&&Math.sqrt(dist2(h.point,e))<best-1)return -1;
  return bi;
}

// ---- the panel ---------------------------------------------------------------------------
// Classes only: a map can also name a model as an entity's classname ("human/dday_ranger_private",
// "human//german_wehrmact_grenadier"), which G_SpawnEntity spawns as that .tik's own class.
// Those are model paths, not classes, so they stay out of the list (add the class and give
// it a "model" key instead).
function modClassOk(c){return !!c&&!/[\/\\]|\.(tik|skd|skb)$/i.test(c);}
function modClasses(){
  const s=new Set(['info_pathnode']);
  const defs=Object.keys(D.defs||{}).filter(c=>{const d=D.defs[c];return d&&d.b&&modClassOk(c);}).sort();
  for(const c of defs)s.add(c);
  for(const e of MAP.ents)if(e.cls&&!e.prims.length&&!WORLDLIKE[e.cls]&&modClassOk(e.cls))s.add(e.cls);
  return [...s];
}
// ---- the list: only the rows in view are in the page ---------------------------------------
// MOD.ents stays the one place the entities live; the list draws the few rows that are
// visible (newest first), and a row's tooltip (the entity's whole text) is built when the
// mouse is over it, so adding or changing hundreds of entities doesn't rebuild hundreds of rows.
const MOD_RH=22;
let _modListRaf=0,_modLastSel=-2;
function modListSetup(L){
  if(L._vp)return;
  L.innerHTML='<div class="mmsg"></div><div class="mvp" style="position:relative;max-height:360px;overflow-y:auto"><div class="msp"></div><div class="mrows" style="position:absolute;left:0;right:0;top:0"></div></div>';
  L._msg=L.querySelector('.mmsg');L._vp=L.querySelector('.mvp');L._sp=L.querySelector('.msp');L._rows=L.querySelector('.mrows');
  L._vp.addEventListener('scroll',()=>{if(_modListRaf)return;
    _modListRaf=requestAnimationFrame(()=>{_modListRaf=0;const l=$('modList');if(l&&MOD)modListDraw(l);});});
  L.addEventListener('mouseover',e=>{const r=e.target.closest('[data-mi]');if(!r||r.title)return;
    const i=+r.dataset.mi,m=MOD.ents[i];if(!m)return;
    r.title=modText(m)+'\n\nShift+click the name: '+(modIsSel(i)?'take it out of the selection':'add it to the selection')+' · Shift+click the square: '+(m.hid?'show':'hide')+' it';});
}
function modRowHtml(m,i){
  const o=modOrigin(m),c=modColour(m),rgb='rgb('+c.map(v=>Math.round(v*255)).join(',')+')',map=modIsMap(m),ch=map&&modEdited(m);
  const tag=map&&m.del?'<span class="mtag ch" style="color:var(--err)" title="one of the map\'s own entities, deleted here: left out of the saved map (not saved yet). Restore puts it back">#'+m.ei+' DEL</span>':map?'<span class="mtag'+(ch?' ch':'')+'" title="'+(ch?'one of the map\'s own entities, changed here (not saved yet)':'one of the map\'s own entities, as the map has it')+'">#'+m.ei+(ch?' changed':' map')+'</span>':'<span class="mtag nw" title="added here, not saved yet">new</span>';
  return '<div class="li'+(modIsSel(i)?' sel':'')+(m.hid||m.del?' hid':'')+'" data-mi="'+i+'"><span class="sw" style="'+(map?'border:2px solid '+rgb+';background:transparent':'background:'+rgb)+'"></span><span class="nm">'+esc(modName(m))+'</span>'+tag+'<span class="ct">( '+o.map(v=>+v.toFixed(1)).join(' ')+' )'+(modBusy(i)?' · editing':'')+'</span></div>';
}
function modListDraw(L){
  modListSetup(L);
  const n=MOD.ents.length,vp=L._vp;
  const msg=(MOD.linking?'<div class="co" style="color:var(--accent)">Click an entity that has a targetname to set '+esc(modName(MOD.linking.from))+'\'s "target" to it (Esc or Make path again cancels).</div>':'')+(MOD.placing?'<div class="co" style="color:var(--accent)">Click anywhere on the map to '+(MOD.placing.move!=null?'move':'place')+' the '+esc(MOD.placing.cls)+' (Esc or '+(MOD.placing.move!=null?'Move':'Add')+' again cancels).</div>':'')+
    (n||MOD.placing?'':'<div class="co">Nothing added yet. Add, then click on the map to place it; new entities stay see-through until saved.</div>');
  if(L._msgH!==msg){L._msgH=msg;L._msg.innerHTML=msg;}
  vp.style.display=n?'':'none';
  L._sp.style.height=(n*MOD_RH)+'px';
  const vh=vp.clientHeight||360;
  // a newly selected row is scrolled into view (newest first: the last entity is the top row)
  if(MOD.sel!==_modLastSel){_modLastSel=MOD.sel;
    if(MOD.sel>=0&&MOD.sel<n){const top=(n-1-MOD.sel)*MOD_RH;
      if(top<vp.scrollTop)vp.scrollTop=top;else if(top+MOD_RH>vp.scrollTop+vh)vp.scrollTop=top+MOD_RH-vh;}}
  const first=Math.max(0,Math.floor(vp.scrollTop/MOD_RH)-8),last=Math.min(n,Math.ceil((vp.scrollTop+vh)/MOD_RH)+8);
  let h='';
  for(let p=first;p<last;p++){const i=n-1-p;h+=modRowHtml(MOD.ents[i],i);}
  L._rows.style.top=(first*MOD_RH)+'px';
  L._rows.innerHTML=h;
}
function modRender(){
  const L=$('modList');if(!L)return;
  modMultiPrune();modHideSync();
  modListDraw(L);                                   // windowed: only the rows in view
  $('bModAdd').classList.toggle('on',!!MOD.placing&&MOD.placing.move==null);
  const has=MOD.ents[MOD.sel]!=null;
  for(const id of['bModEdit','bModMove','bModTrim','bModYaw','bModLink','bModEye','bModFly','bModSf','bModDel'])$(id).disabled=!has;
  $('bModLink').classList.toggle('on',!!MOD.linking);
  const nsel=modSelCount();
  $('bModDup').disabled=!nsel&&!(MOD.placing&&MOD.placing.copy);
  $('bModDup').classList.toggle('on',!!MOD.placing&&!!MOD.placing.copy);
  $('bModDup').textContent=nsel>1?'Copy ('+nsel+')':'Copy';
  $('bModHUndo').disabled=!MOD.undo.length;$('bModHRedo').disabled=!MOD.redo.length;
  $('bModHUndo').title='Undo the last change to Modify\'s entities ('+MOD.undo.length+' to undo), back to none added\n\nHotkey: Alt+Z';
  $('bModHRedo').title='Redo the last change undone ('+MOD.redo.length+' to redo)\n\nHotkey: Alt+Y or Alt+Shift+Z';
  if(nsel>1&&!MOD.trim&&!(MOD.placing&&MOD.placing.move!=null))$('bModMove').disabled=$('bModTrim').disabled=false;
  lineDirty=true;                                   // its links and facing arrows
  // Move and Trim origin each shut the other off while on
  const moving=!!MOD.placing&&MOD.placing.move!=null;
  if(MOD.trim)$('bModMove').disabled=true;
  if(moving)$('bModTrim').disabled=true;
  $('bModMove').classList.toggle('on',moving);
  $('bModTrim').classList.toggle('on',MOD.trim);$('bModEdit').classList.toggle('on',MOD.edit>=0);
  const cur=MOD.ents[MOD.sel];
  const rest=cur&&modIsMap(cur)&&(cur.del||modKvEdited(cur));
  $('bModDel').textContent=rest?'Restore':'Delete';
  $('bModDel').title=rest?'Put back the map\'s own keys for this entity and keep it in the saved map':cur&&modIsMap(cur)?'Delete this map entity: it is left out of the saved map (flagged DEL; Restore or Undo puts it back)\n\nHotkey: Delete':'Remove the entity (every selected one)\n\nHotkey: Delete';
  if(modSelEnts(false).length>1)$('bModDel').textContent='Delete ('+modSelEnts(false).length+')';
  const nw=MOD.ents.filter(m=>!modIsMap(m)),ch=MOD.ents.filter(m=>modIsMap(m)&&modEdited(m));
  $('bModSaveBsp').disabled=$('bModSaveMap').disabled=$('bModCopy').disabled=!(nw.length||ch.length);
  modStatSoon();
  sfRender();
  // a selected entity Modify can't take, and why: one the level script spawns (it isn't in the
  // .bsp or the .map), a static model of a .bsp (its static model lump, not its entity lump),
  // or a brush entity (only point entities are modified here)
  {const ei=selFocusEnt(),e=ei>0&&MAP&&MAP.ents[ei],el=$('modScr');let t='';
    if(e&&!cur&&!modTakes(ei)){
      if(e.scr)t='This entity is spawned by the level script ('+scrWhere(e.scr.f,e.scr.l)+'): it can only be modified in the level script, not in the map viewer.';
      else if(D.bsp&&isStaticProp(ei))t='This is a static model, not a .bsp entity: the map compiler moved it into the .bsp\'s static model lump, so it isn\'t in the entity lump and can\'t be modified in the map viewer. Change it in the map\'s .map source and compile again.';
      else if(ENTS[ei]&&ENTS[ei].hasGeo&&!WORLDLIKE[e.cls])t='This is a brush entity: only point entities can be modified in the map viewer.';}
    el.style.display=t?'':'none';el.textContent=t;}
}
// the heavy part of the render (path checks, limits, the status line), once per frame at most
let _modStatRaf=0;
function modStatSoon(){if(_modStatRaf)return;_modStatRaf=requestAnimationFrame(()=>{_modStatRaf=0;if(MAP&&MOD&&$('modStat'))modStatNow();});}
function modStatNow(){
  const nw=MOD.ents.filter(m=>!modIsMap(m)),ch=MOD.ents.filter(m=>modIsMap(m)&&modEdited(m));
  const A=PA_C&&PA_C.n0!=null?PA_C:null,nn=nw.filter(modIsNode).length;
  const LM=(nw.length||ch.length)?modLimits():null;
  const IS=(nw.length||ch.length)?paIssues():null;
  if(IS&&IS.n){const keys=[...IS.node].filter(([i,l])=>l.some(x=>x.lv)).map(([i])=>String(i)).join(',');
    if(keys!==MOD.issKeys){MOD.issKeys=keys;
      const lines=[];for(const[i,l]of IS.node)for(const x of l)if(x.lv)lines.push(x.t);
      flash('AI paths: '+lines[0]+(lines.length>1?' (+'+(lines.length-1)+' more: the node cards say)':''));
      for(const t of lines)hostLog('paths',t);}}
  else MOD.issKeys='';
  $('modStat').textContent=(nw.length||ch.length)?nw.length+' new ('+nn+' path node'+(nn===1?'':'s')+'), '+ch.length+' changed'+
    (A?' · '+(A.n)+' nodes in the paths':'')+(PA_GEN?' · paths worked out here (no .pth, '+PA_GEN.ms+' ms)':'')+
    ' · real entities '+LM.real+' of '+LM.rmax+' · path nodes '+LM.nodes+' of 4096'+(IS&&IS.n?' · '+IS.n+' path problem'+(IS.n===1?'':'s')+' (marked in the view)':''):'';
  // over a limit (a classname changed in Edit parameters can get there): red, and why
  const over=LM&&(LM.real>LM.rmax||LM.nodes>MAX_PATHNODES),near=LM&&!over&&(LM.real>LM.rmax-(LM.mp?96:64)||LM.nodes>MAX_PATHNODES-200||(IS&&IS.n));
  $('modStat').style.color=over?'var(--selcol)':near?'#ffd040':'';
  $('modStat').title=over?'Past the game\'s limit: '+(LM.real>LM.rmax?'more real entities than its '+LM.rmax+' slots (with one player; "no free edicts") ':'')+(LM.nodes>MAX_PATHNODES?'more than 4096 path nodes ("Exceeded MAX_PATHNODES!")':'')+'. The saved map won\'t load.':near?(IS&&IS.n?[...IS.node.values()].flat().filter(x=>x.lv).map(x=>x.t).join('\n'):'Close to the game\'s limit'+(LM.mp?' (in multiplayer each player slot takes one more entity slot)':'')):'';
  simPanel();
}
// Edit parameters' place: where it was dragged, kept inside the 3D view
function modEdPlace(){
  const ed=$('modEd'),st=$('stage');if(!ed||!st)return;
  if(!MOD.edPos){ed.style.left='14px';ed.style.top='14px';return;}
  const w=ed.offsetWidth||380,h=ed.offsetHeight||300;
  const x=Math.max(0,Math.min(st.clientWidth-Math.min(w,st.clientWidth),MOD.edPos.x)),y=Math.max(0,Math.min(st.clientHeight-40,MOD.edPos.y));
  ed.style.left=x+'px';ed.style.top=y+'px';
}
// ---- the class list: searchable, as the Model Viewer's attach-to-bone list ----------------
// A popup beside the button: the classes (info_pathnode first, then the entity definitions'
// point classes and the map's own) with how many the map has; typing filters them (every
// word must appear), arrows move, Enter or a click takes one, Esc closes.
const MCL={el:null,back:null,f:'',hot:0,hits:[],all:null};
function mclAll(){
  if(MCL.all)return MCL.all;const n=new Map();
  for(let ei=1;ei<MAP.ents.length;ei++){const c=MAP.ents[ei].cls;n.set(c,(n.get(c)||0)+1);}
  return MCL.all=modClasses().map(c=>({c:c,n:n.get(c)||0,d:!!(D.defs||{})[c]}));
}
function mclHits(){const w=MCL.f.toLowerCase().split(/\s+/).filter(Boolean);
  return mclAll().filter(x=>w.every(t=>x.c.includes(t)));}
function mclClose(){if(MCL.back)MCL.back.remove();MCL.el=MCL.back=null;document.removeEventListener('keydown',mclKey,true);}
function mclPick(c){MOD.cls=c;$('modClsBtn').querySelector('.albl').textContent=c;mclClose();
  if(MOD.placing&&MOD.placing.move==null)modAdd(c);}           // placing one: place this class instead
function mclOpen(){
  mclClose();MCL.f='';MCL.hot=0;
  MCL.back=document.createElement('div');MCL.back.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  MCL.back.onclick=ev=>{if(!MCL.el||!MCL.el.contains(ev.target))mclClose();};
  document.body.appendChild(MCL.back);
  const el=MCL.el=document.createElement('div');el.className='amPanel';
  el.innerHTML='<div class="amHead"><span class="amPathTxt">entity classes</span><span id="mclCnt"></span></div>'+
    '<input class="amSearch" type="text" id="mclSearch" placeholder="filter classes\u2026" spellcheck="false"><div class="amBody" id="mclBody"></div>';
  MCL.back.appendChild(el);
  const se=$('mclSearch');se.oninput=()=>{MCL.f=se.value.trim();MCL.hot=0;mclRender();};
  el.addEventListener('mousedown',ev=>{if(ev.target===se)return;ev.preventDefault();});
  document.addEventListener('keydown',mclKey,true);
  mclRender();
  const cur=el.querySelector('.amItem.sel'),bd=$('mclBody');if(cur)bd.scrollTop=cur.offsetTop-bd.offsetTop-(bd.clientHeight-cur.offsetHeight)/2;
  se.focus();
}
function mclPlace(){
  const el=MCL.el,b=$('modClsBtn');if(!el||!b)return;
  const r=b.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight,w=el.offsetWidth||340;
  let left=r.left-6-w;if(left<4)left=Math.min(r.right+6,Math.max(4,vw-4-w));
  el.style.left=left+'px';el.style.maxHeight=(vh-8)+'px';
  const h=Math.min(el.getBoundingClientRect().height,vh-8);el.style.top=Math.max(4,Math.min(r.top,vh-4-h))+'px';
}
function mclRender(){
  const bd=$('mclBody');if(!bd)return;const H=MCL.hits=mclHits();
  MCL.hot=Math.max(0,Math.min(MCL.hot,H.length-1));
  bd.innerHTML=H.slice(0,600).map((x,i)=>'<div class="amItem'+(i===MCL.hot?' hot':'')+(x.c===MOD.cls?' sel':'')+'" data-c="'+esc(x.c)+'" title="'+esc(x.c)+(x.n?': '+x.n+' in this map':'')+(x.d?'':' (no entity definition: a 16-unit box)')+'">'+
    '<span class="lbl">'+esc(x.c)+'</span><span class="cnt">'+(x.n?x.n:'')+'</span></div>').join('')+
    (H.length?'':'<div class="amNote">no class matches that</div>')+(H.length>600?'<div class="amNote">… '+(H.length-600)+' more: type more of the name</div>':'');
  bd.onclick=ev=>{const r=ev.target.closest('[data-c]');if(r){ev.stopPropagation();mclPick(r.dataset.c);}};
  $('mclCnt').textContent=H.length+' / '+mclAll().length;
  mclPlace();
}
function mclKey(ev){
  if(!MCL.el)return;
  if(ev.key==='Escape'){mclClose();ev.preventDefault();ev.stopPropagation();return;}
  if(ev.key==='Enter'){const x=MCL.hits[MCL.hot];if(x)mclPick(x.c);ev.preventDefault();ev.stopPropagation();return;}
  if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){MCL.hot+=ev.key==='ArrowDown'?1:-1;mclRender();
    const h=MCL.el.querySelector('.amItem.hot');if(h)h.scrollIntoView({block:'nearest'});ev.preventDefault();ev.stopPropagation();return;}
  ev.stopPropagation();
}
// the new entities as entity-lump text, in the order added
function modEntsText(){return MOD.ents.filter(m=>!modIsMap(m)).map(modText).join('\n')+'\n';}
// the map's entities changed here: by entity number (the decompiled .map keeps the entity
// lump's order), with the class and origin they had, to check against the .bsp
function modSets(){return MOD.ents.filter(m=>modIsMap(m)&&modEdited(m)).map(m=>({ei:m.ei,cls:MAP.ents[m.ei].cls,
  origin:parseVec(edKey({kv:m.orig},'origin'),3),kv:m.del?m.orig:m.kv,del:!!m.del}));}
// the .map with the changes: each changed (point) entity's block written again, the new ones added
function modMapText(){
  let t=D.srcText;const ch=MOD.ents.filter(m=>modIsMap(m)&&modEdited(m)).sort((a,b)=>MAP.ents[b.ei].ts-MAP.ents[a.ei].ts);
  for(const m of ch){const e=MAP.ents[m.ei];if(!(e.ts>=0&&e.te>e.ts))continue;t=t.slice(0,e.ts)+(m.del?'':modText(m))+t.slice(e.te);}
  const add=MOD.ents.filter(m=>!modIsMap(m));
  if(add.length)t=t.replace(/\s*$/,'\n')+'// added in MOHAA Map Viewer\'s MODIFY\n'+add.map(modText).join('\n')+'\n';
  return t;
}
function modCopyText(){const ch=MOD.ents.filter(m=>modIsMap(m)&&modEdited(m)&&!m.del);
  return (ch.length?'// changed (entity number in the map)\n'+ch.map(m=>'// entity '+m.ei+'\n'+modText(m)).join('\n')+'\n// new\n':'')+modEntsText();}
// What Save would write, to tell whether it has been saved: the new entities' text and the
// map's changed ones (modSaved keeps it once a save goes through)
function modSaveKey(){return JSON.stringify([modEntsText(),modSets().map(x=>[x.ei,x.kv,x.del?1:0])]);}
// MODIFY's changes not saved yet as a .bsp or .map: {nw new, ch changed}, else null
function modUnsaved(){
  if(!MOD||!MOD.ents)return null;
  const nw=MOD.ents.filter(m=>!modIsMap(m)).length,ch=MOD.ents.filter(m=>modIsMap(m)&&modEdited(m)).length;
  if(!nw&&!ch)return null;
  return modSaveKey()===MOD.savedKey?null:{nw:nw,ch:ch};
}
// the launcher's close question answered with Save as: save, then close once it is written
function modDiscardClose(){MOD.leaving=true;MOD.savedKey=modSaveKey();_modBkKey=null;modBackupNow();
  try{window.chrome.webview.postMessage('mohaa-close');}catch(_e){}}
function modSaveThenClose(kind){MOD.closeAfter=true;modSave(kind==='map'?'map':'bsp');}
function modSaveCancelled(){MOD.closeAfter=false;MOD.pendKey=null;flash('Not saved');}
function modSave(kind){
  if(MOD.edit>=0)modEditClose(true);
  if(MOD.trim)modTrim(false);
  const sets=modSets(),nw=MOD.ents.filter(m=>!modIsMap(m));
  if(!sets.length&&!nw.length)return;
  const nodes=nw.filter(modIsNode).length,have=pnEnts().length;
  if(have+nodes>4096){MOD.closeAfter=false;flash('More than 4096 path nodes: the game can\'t load that many');return;}
  MOD.pendKey=modSaveKey();
  const req={kind:kind,ents:nw.length?modEntsText():'',set:sets,mapText:kind==='map'?modMapText():null,src:D.srcFile||'',vpath:D.path||'',mapFile:(D.bsp&&D.bsp.mapFile)||'',isBsp:D.kind==='bsp',name:D.name||''};
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-modify-save\n'+JSON.stringify(req));
    flash('Saving: choose where in the launcher');return;}}catch(_e){}
  // no launcher: a .map can still be saved from the page; a .bsp needs the launcher
  if(kind==='map'){const txt=modMapText();
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([txt],{type:'text/plain'}));
    a.download=(D.name||'map')+'_modified.map';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);}
  else flash('Save as .bsp works from the launcher (open this map there); Copy gives the new entities as entity-lump text');
}
// the launcher's answer
function modSaved(ok,msg){flash(msg);$('modStat').textContent=msg;
  if(ok&&MOD.pendKey!=null){MOD.savedKey=MOD.pendKey;modBackupNow();}
  MOD.pendKey=null;
  const close=MOD.closeAfter;MOD.closeAfter=false;
  if(ok&&close)closeViewer();}
function modInit(){
  $('modClsBtn').onclick=()=>MCL.el?mclClose():mclOpen();
  window.addEventListener('resize',()=>{if(MCL.el)mclClose();});
  $('bModAdd').onclick=()=>modAdd(MOD.cls);
  $('bModEdit').onclick=()=>MOD.edit>=0?modEditClose(true):modEditOpen(MOD.sel);
  $('bModTrim').onclick=()=>modTrim();
  $('bModMove').onclick=()=>modMove();
  $('bModLink').onclick=()=>modLinkStart();
  $('bModEye').onclick=()=>{const m=MOD.ents[MOD.sel];if(!m)return;
    const v=eyeViewFrom(modCls(m),modKvl(m),modOrigin(m),modName(m),-1,true);if(!v)return;
    flyTo(v.pos,v.ang[1],v.ang[0],-v.ang[2]);requestDraw();flash(v.flash);};
  $('bModFly').onclick=modFly;
  $('bModSf').onclick=toggleSfMenu;
  $('bModYaw').onclick=modYaw;
  $('bModDel').onclick=()=>modRemoveSel();
  $('bModDup').onclick=()=>modCopySel();
  $('bModHUndo').onclick=()=>modUndoGo(-1);
  $('bModHRedo').onclick=()=>modUndoGo(1);
  $('bModSaveBsp').onclick=()=>modSave('bsp');
  $('bModSaveMap').onclick=()=>modSave('map');
  $('bModCopy').onclick=()=>{copyText(modCopyText());flash('The new and changed entities are copied');};
  const st=$('modStep');st.value=MOD.stepI;$('modStepV').textContent=MOD_STEPS[MOD.stepI];
  st.oninput=()=>{MOD.stepI=+st.value;$('modStepV').textContent=MOD_STEPS[MOD.stepI];slidersPost();};
  // as the Find lists: Shift+click a row's square hides / shows it, Shift+click the selected
  // (green) row deselects it
  $('modList').addEventListener('click',e=>{const r=e.target.closest('[data-mi]');if(!r)return;const i=+r.dataset.mi;
    if(e.shiftKey&&e.target.closest('.sw')){modToggleHide(i);return;}
    if(e.shiftKey){modToggleSel(i);return;}
    // a click on the row already selected (green), so also the second click of a
    // double-click: Fly to
    if(!e.shiftKey&&i===MOD.sel){modFly();return;}
    modSelect(i);});
  $('modTxt').addEventListener('input',modEditInput);
  $('modTxt').addEventListener('keydown',e=>{if(e.key==='Escape'){modEditClose(true);e.preventDefault();e.stopPropagation();return;}
    const k=e.key.toLowerCase();
    if((e.ctrlKey||e.metaKey)&&(k==='z'||k==='y')){modHistGo(k==='y'||e.shiftKey?1:-1);e.preventDefault();e.stopPropagation();}});
  $('bModDone').onclick=()=>modEditClose(true);
  // the box moves by its title bar, kept inside the 3D view (and where it was left)
  try{const p=JSON.parse(LS.get('mohaaMapModEd')||'null');if(p&&isFinite(p.x)&&isFinite(p.y))MOD.edPos=p;}catch(_e){}
  modEdPlace();
  $('modEdHead').addEventListener('mousedown',e=>{if(e.button!==0)return;e.preventDefault();
    const ed=$('modEd'),r=ed.getBoundingClientRect(),st=$('stage').getBoundingClientRect();
    const dx=e.clientX-r.left,dy=e.clientY-r.top;
    const mv=ev=>{MOD.edPos={x:ev.clientX-st.left-dx,y:ev.clientY-st.top-dy};modEdPlace();};
    const up=()=>{window.removeEventListener('mousemove',mv,true);window.removeEventListener('mouseup',up,true);
      try{LS.set('mohaaMapModEd',JSON.stringify(MOD.edPos));}catch(_e){}};
    window.addEventListener('mousemove',mv,true);window.addEventListener('mouseup',up,true);});
  window.addEventListener('resize',modEdPlace);
  $('bModUndo').onclick=()=>modHistGo(-1);
  $('bModRedo').onclick=()=>modHistGo(1);
  modRender();
}

// ============================================================================
//  SIMULATE: a model flying an info_splinepath path, as a script's followpath does
// ============================================================================
// ScriptSlave::FollowPath / CreatePath / FollowingPath (fgame/scriptslave.cpp) with
// BSpline::EvalClamp (fgame/bspline.cpp): the path is the given node and each next one its
// "target" names (G_FindTarget: the first entity with that targetname; a target that isn't
// an info_splinepath ends it), until one has no target or the path comes back to the
// start. Each node gives the spline its origin, its angles (as the forward vector and the
// roll) and its "speed" (1 if it has none). splineTime starts at -2; every server frame
// (0.05 s) the model is sent to the position and angles EvalClamp gives for it, and
// splineTime moves on by 0.05 times the speed EvalClamp blends from the nodes (so a speed
// is in nodes per second), until it passes the number of nodes less 2. The game draws the
// model between its frames; so does this.
// The path starts at the first node: the selected node's chain followed back through what
// targets it (the engine keeps the last node, in spawn order, that targets a node as its
// previous one), up to a node nothing targets.
const SIM={run:false,t0:0,mul:1,frames:null,rc:null,chain:null,cur:null,pick:'',R:null,cache:new Map(),fail:new Map(),
  busy:'',list:null,listErr:'',asked:false,texi:new Map(),txAt:0,camT:0};
const SIM_FT=0.05, SIM_MAX=20*60*10;       // a server frame; at most 10 minutes of frames
const SIM_LS='mohaaMapViewerSimModel';
function simHost(){try{return !!(window.chrome&&window.chrome.webview);}catch(_e){return false;}}
function simPost(m){try{if(simHost()){window.chrome.webview.postMessage(m);return true;}}catch(_e){}return false;}
// The node Simulate starts from: the selected info_splinepath (a map entity, or a new one
// Modify placed): 'e<entity>' / 'm<Modify id>', else null.
function simFocus(){
  if(selAll().n>1)return null;               // several selected: no spline Simulate
  const m=MOD.ents[MOD.sel];
  if(m&&!modIsMap(m))return modCls(m)==='info_splinepath'?'m'+m.id:null;
  const ei=m&&modIsMap(m)?m.ei:selFocusEnt();
  if(!(ei>0)||ei>=MAP.ents.length)return null;
  const mm=MOD.ents.find(x=>x.ei===ei),cls=mm&&modEdited(mm)?modCls(mm):String(MAP.ents[ei].kvl.classname||'').toLowerCase();
  return cls==='info_splinepath'?'e'+ei:null;
}
// Every entity as the game would spawn it (Modify's changes in, its new ones after the
// map's), and the first one with each targetname.
// Modify's keys as the game takes them: "$targetname" / "#speed" name the key too (the
// first such form wins over a plain one after it; spawnKeys does the same for the map's)
function simKvl(m){
  const k=modKvl(m),SK=new Set(D.sk||[]),pre=new Map(),plain=new Map();
  m.kv.forEach(([a,v],i)=>{const l=a.toLowerCase(),c=l[0];
    if((c==='$'||c==='#')&&SK.has(l.slice(1))){const n=l.slice(1);if(!pre.has(n))pre.set(n,[i,c==='#'?String(parseInt(v,10)||0):v]);}
    else if(!plain.has(l))plain.set(l,i);});
  for(const[n,[i,v]]of pre){const p=plain.get(n);if(p==null||i<p)k[n]=v;}
  return k;
}
function simWorld(){
  const all=[],tn=new Map(),modOf=new Map();
  for(const m of MOD.ents)if(modIsMap(m))modOf.set(m.ei,m);
  const add=(key,kvl,ei)=>{const n={key:key,kvl:kvl,ei:ei,cls:String(kvl.classname||'').toLowerCase()};all.push(n);
    const t=kvl.targetname;if(t&&!tn.has(t))tn.set(t,n);};
  for(let ei=1;ei<MAP.ents.length;ei++){const m=modOf.get(ei);if(m&&m.del)continue;add('e'+ei,m&&modEdited(m)?simKvl(m):MAP.ents[ei].kvl,ei);}
  for(const m of MOD.ents)if(!modIsMap(m))add('m'+m.id,simKvl(m),-1);
  return{all:all,tn:tn};
}
function simNodeName(n){return n.kvl.targetname?'$'+n.kvl.targetname:n.ei>0?'entity '+n.ei:'a new node';}
// The path through the node 'key': its nodes from the first, what ends it, and its frames.
function simChain(key){
  const W=simWorld();let s=null;
  for(const n of W.all)if(n.key===key){s=n;break;}
  if(!s||s.cls!=='info_splinepath')return null;
  const isS=n=>!!n&&n.cls==='info_splinepath';
  const next=n=>{const t=n.kvl.target;return t?W.tn.get(t)||null:null;};
  const prev=new Map();
  for(const n of W.all)if(isS(n)){const q=next(n);if(isS(q)&&q!==n)prev.set(q,n);}
  let head=s;const back=new Set([s]);
  for(let p=prev.get(head);p&&!back.has(p);p=prev.get(head)){back.add(p);head=p;}
  if(prev.get(head)===s&&head!==s)head=s;     // a closed loop: it starts where it was selected
  const nodes=[],seen=new Set();let end='', n=head;
  while(n){
    if(seen.has(n)){end=n===head?'its last node leads back to the first':'it runs back into '+simNodeName(n)+' (the game would follow that loop for ever)';break;}
    seen.add(n);nodes.push(n);
    if(nodes.length>=4096){end='4096 nodes';break;}
    const t=n.kvl.target;
    if(!t){end='';break;}
    const q=W.tn.get(t);
    if(!q){end=simNodeName(n)+'\'s target $'+t+' isn\'t in the map';break;}
    if(!isS(q)){end=simNodeName(n)+'\'s target $'+t+' is a '+q.cls+', not an info_splinepath';break;}
    n=q;
  }
  const P=nodes.map(x=>{const k=x.kvl,o=parseVec(k.origin,3)||(x.ei>0&&ENTS[x.ei]&&ENTS[x.ei].origin)||[0,0,0];
    let sp=parseFloat(k.speed);if(!isFinite(sp))sp=1;return{n:x,o:o.slice(),a:entAngles(k),s:sp};});
  const ch={key:key,head:head,nodes:P,end:end,sel:s};
  ch.fr=simFrames(ch);
  return ch;
}
// BSpline::EvalClamp at t: position, angles ( pitch yaw roll ) and speed
function simEval(C,t){
  const n=C.p.length,seg=Math.floor(t),u=t-seg,u2=u*u,u3=u2*u,m=1-u;
  const B=[m*m*m/6,(3*u3-6*u2+4)/6,(-3*u3+3*u2+3*u+1)/6,u3/6];
  const P=[0,0,0],A=[0,0,0];let sp=0,rl=0;
  for(let i=0;i<4;i++){let j=seg+i;if(j<0)j=0;else if(j>=n)j=n-1;const b=B[i],p=C.p[j],f=C.f[j];
    P[0]+=p[0]*b;P[1]+=p[1]*b;P[2]+=p[2]*b;A[0]+=f[0]*b;A[1]+=f[1]*b;A[2]+=f[2]*b;sp+=C.s[j]*b;rl+=C.r[j]*b;}
  // Vector::toAngles: ( -pitch yaw 0 ), both 0..360; then the blended roll
  let yaw,pitch;
  if(A[0]===0&&A[1]===0){yaw=0;pitch=A[2]>0?90:270;}
  else{yaw=Math.atan2(A[1],A[0])*180/Math.PI;if(yaw<0)yaw+=360;
    pitch=Math.atan2(A[2],Math.hypot(A[0],A[1]))*180/Math.PI;if(pitch<0)pitch+=360;}
  return{p:P,a:[-pitch,yaw,rl],s:sp};
}
// the control points (BSplineControlPoint::Set) and every server frame of the flight
function simFrames(ch){
  const C={p:[],f:[],r:[],s:[]};
  for(const x of ch.nodes){C.p.push(x.o);C.f.push(anglesAxis(x.a)[0]);
    let r=x.a[2];if(r>180)r-=360;if(r<-180)r+=360;C.r.push(r);C.s.push(x.s);}
  const F=[],end=C.p.length-2;let t=-2,cap=false;
  if(C.p.length)while(t<=end){if(F.length>=SIM_MAX){cap=true;break;}const e=simEval(C,t);F.push(e);t+=SIM_FT*e.s;}
  if(!F.length&&C.p.length)F.push(simEval(C,-2));
  // the curve it flies, a point every tenth of a node
  const curve=[];
  if(C.p.length>1){for(let u=-2;u<end;u+=0.1)curve.push(simEval(C,u).p);curve.push(simEval(C,end).p);}
  return{F:F,cap:cap,C:C,curve:curve};
}
function simDur(fr){return Math.max(0,fr.F.length-1)*SIM_FT;}
function simSecs(x){return x<60?x.toFixed(1)+' s':Math.floor(x/60)+' min '+(x%60).toFixed(0)+' s';}
function lerpAng(a,b,u){let d=b-a;d=((d%360)+540)%360-180;return a+d*u;}
// ---- the panel -----------------------------------------------------------------------------
function simPanel(){
  if(!$('simSect')||!MAP)return;
  const key=simFocus(),nf=(!key&&!SIM.run)?actFocus():null,show=!!key||SIM.run||!!nf;
  $('simSect').style.display=show?'':'none';
  // a path node shows the actor's controls instead of the spline's
  $('simSpl').style.display=nf?'none':'';$('simNd').style.display=nf?'':'none';
  actPanel(nf);
  if(!show||nf){SIM.chain=null;return;}
  if(key&&(!SIM.chain||SIM.chain.key!==key||!SIM.run))SIM.chain=simChain(key);
  const ch=SIM.run?SIM.rc:SIM.chain;
  $('bSim').disabled=SIM.run||!SIM.chain;$('bSimReset').disabled=!SIM.run;
  let s='';
  if(ch){const n=ch.nodes.length,last=ch.nodes[n-1];
    s='Path from '+simNodeName(ch.head.n||ch.head)+(n>1?' to '+simNodeName(last.n):'')+': '+n+' node'+(n===1?'':'s');
    if(ch.end)s+='\nEnds where '+ch.end;
    if(ch.fr.cap)s+='\nIts speed never gets it to the end: the first 10 minutes are shown';
    if(n<2)s+='\nOne node: the model stays on it';
    const sl=ch.nodes.filter(x=>x.s<=0);if(sl.length)s+='\n'+sl.length+' node'+(sl.length>1?'s have':' has')+' a speed of 0 or less';}
  $('simSum').textContent=s;
  simModelText();simTimeText(performance.now(),true);
}
function simModelText(){
  const e=$('simModel');if(!e)return;
  const p=SIM.pick;let t=p?p.replace(/^models\//,''):'placeholder box';
  if(p&&SIM.busy===p)t+=' (building…)';
  else if(p&&SIM.fail.has(p))t+=' (can\'t be drawn: the box flies instead)';
  e.textContent=t;e.title=p?(SIM.fail.get(p)||p):'A plain box with a nose; Choose… picks a model';
}
function simTimeText(now,force){
  const e=$('simTime');if(!e)return;
  if(!force&&now-SIM.txAt<100)return;SIM.txAt=now;
  const ch=SIM.run?SIM.rc:SIM.chain;
  if(!ch){e.textContent='';return;}
  const d=simDur(ch.fr);
  if(SIM.run){const t=Math.min(d,(now-SIM.t0)/1000*SIM.mul);e.textContent=simSecs(t)+' of '+simSecs(d)+' (game time)';}
  else e.textContent='Takes '+simSecs(d)+' at its nodes\' speeds';
}
// ---- running ---------------------------------------------------------------------------------
function simStart(){
  if(SIM.run)return;
  const key=simFocus();if(!key){flash('Select an info_splinepath first');return;}
  const ch=simChain(key);if(!ch||!ch.nodes.length){flash('This info_splinepath has no path to fly');return;}
  SIM.rc=ch;SIM.chain=ch;SIM.frames=ch.fr.F;SIM.run=true;SIM.t0=performance.now();SIM.cur=null;SIM.camT=0;
  simUseModel();
  if($('simEye').checked&&!$('simCam').checked)simEyeStart(ch);
  simTick(performance.now());
  simPanel();requestDraw();
  flash('Simulating '+ch.nodes.length+' node'+(ch.nodes.length===1?'':'s')+' from '+simNodeName(ch.head)+': '+simSecs(simDur(ch.fr))+
    (ch.fr.cap?' (its speed never gets it to the end: 10 minutes shown)':''));
}
function simReset(done){
  if(!SIM.run&&!done)return;
  SIM.run=false;SIM.rc=null;SIM.cur=null;SIM.frames=null;if(SIM.R)SIM.R.n=0;
  simPanel();requestDraw();
  if(done)flash('Simulation finished');
}
// each frame while it runs: where the model is (between two server frames), the camera if it
// follows; the end resets it
function simTick(now){
  const F=SIM.frames;if(!F||!F.length){simReset(true);return true;}
  const x=(now-SIM.t0)/1000*SIM.mul/SIM_FT;
  if(x>=F.length-1){simReset(true);return true;}
  const i=Math.min(F.length-1,Math.floor(x)),j=Math.min(F.length-1,i+1),u=Math.min(1,x-i),a=F[i],b=F[j];
  const p=[0,1,2].map(k=>a.p[k]+(b.p[k]-a.p[k])*u),an=[0,1,2].map(k=>lerpAng(a.a[k],b.a[k],u));
  SIM.cur={p:p,a:an};
  if(SIM.R&&gl)simInst(SIM.R,p,an);
  if($('simCam').checked)simFollow(p,an,now);
  simTimeText(now,false);
  return true;
}
// the model's place in the view: its angles and position, the light grid's light there
// (RB_GetEntityGridLighting's brightening), not pickable
function simInst(R,p,a){
  const ax=anglesAxis(a),G=lightGrid();let c=[255,255,255];
  if(G){const v=lgFast(G,p).slice(0,3).map(x=>x*2),m=Math.max(v[0],v[1],v[2]);c=m>255?v.map(x=>x*255/m):v;}
  const d=new Float32Array([ax[0][0],ax[1][0],ax[2][0],p[0], ax[0][1],ax[1][1],ax[2][1],p[1], ax[0][2],ax[1][2],ax[2][2],p[2],
    0, c[0]/255,c[1]/255,c[2]/255, -1, -1, 0]);
  gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,d,gl.DYNAMIC_DRAW);R.n=1;
}
// Camera zoom: how far behind the model the camera follows, 24 to 4096 units (the slider's
// 0..100, on a log scale)
function simZoomDist(){const v=+$('simZoom').value;return 24*Math.pow(4096/24,v/100);}
function simZoomShow(){$('simZoomV').textContent=Math.round(simZoomDist());slidersPost();}
// the model's size, for how high above it Follow rides
function simSize(){const b=SIM.R&&SIM.R.M&&SIM.R.M.b;return b?Math.max(16,Math.hypot(b[1][0]-b[0][0],b[1][1]-b[0][1],b[1][2]-b[0][2])/2):32;}
// Follow: behind the model (its heading) and a little above it, looking at it, catching up
// smoothly. Follow and Eye view: behind it along its own facing, at its exact angles
// (pitch, yaw and roll; the page's roll turns the other way to the game's).
function simFollow(p,a,now){
  const dist=simZoomDist();
  if($('simEye').checked){const ax=anglesAxis(a),f=ax[0],u=ax[2];
    for(let i=0;i<3;i++)cam.pos[i]=p[i]-f[i]*dist+u[i]*(dist*0.12+simSize()*0.5);
    let pt=((a[0]%360)+540)%360-180,rl=((a[2]%360)+540)%360-180;
    cam.yaw=a[1];cam.pitch=pt;cam.roll=-rl;camChanged();SIM.camT=now;return;}
  const y=a[1]*Math.PI/180,want=[p[0]-Math.cos(y)*dist,p[1]-Math.sin(y)*dist,p[2]+simSize()*0.4+dist*0.15];
  const dt=SIM.camT?Math.min(0.1,(now-SIM.camT)/1000):1;SIM.camT=now;
  const k=Math.min(1,dt*5);
  for(let i=0;i<3;i++)cam.pos[i]+=(want[i]-cam.pos[i])*k;
  const d=[p[0]-cam.pos[0],p[1]-cam.pos[1],p[2]-cam.pos[2]];
  cam.yaw=Math.atan2(d[1],d[0])*180/Math.PI;cam.pitch=-Math.atan2(d[2],Math.hypot(d[0],d[1]))*180/Math.PI;cam.roll=0;
  camChanged();
}
// Eye view alone: the camera on the path's first node, at its angles, where it stays
function simEyeStart(ch){
  const n=ch.nodes[0];if(!n)return;
  const a=n.a,pt=((a[0]%360)+540)%360-180,rl=((a[2]%360)+540)%360-180;
  flyAnim=null;cam.pos=n.o.slice();cam.yaw=a[1];cam.pitch=pt;cam.roll=-rl;camChanged();
}
// ---- the model -------------------------------------------------------------------------------
// The picked model's mesh, once it is here: one the map places (in the page already), else
// built by the launcher from the paks (mohaa-sim-build); the box until then.
function simUseModel(){
  const p=SIM.pick;
  if(SIM.R)SIM.R.n=0;
  SIM.R=null;
  if(!p){simModelText();return;}
  if(SIM.cache.has(p)){SIM.R=SIM.cache.get(p);}
  else if(!SIM.fail.has(p)){
    const mi=(D.models||[]).findIndex(M=>String(M.p||'').toLowerCase()===p);
    if(mi>=0&&gl){try{const R=modelR(D.models[mi],D);SIM.cache.set(p,R);SIM.R=R;}catch(e){SIM.fail.set(p,String(e.message||e));}}
    else if(SIM.busy!==p){if(simPost('mohaa-sim-build\n'+p))SIM.busy=p;else SIM.fail.set(p,'Only the map\'s own models can fly in a browser: open the map in the Map Viewer for the rest');}
  }
  if(SIM.R&&SIM.run&&SIM.cur)simInst(SIM.R,SIM.cur.p,SIM.cur.a);
  simModelText();requestDraw();
}
function simSetPick(p){
  SIM.pick=String(p||'').toLowerCase();LS.set(SIM_LS,SIM.pick);
  simUseModel();simClose();
}
// A picture the model needs: the map's own entry when it has the same shader, else a new
// entry (kept out of the Textures list and Find: they list the map's faces and models).
function simTexIndex(t,P){
  const e=TEXI.get(t.n);if(e&&!e.standin)return e.i;
  if(SIM.texi.has(t.n))return SIM.texi.get(t.n);
  const i=TEX.length,te=Object.assign({},t,{i:i,sim:1});delete te.b;delete te.gb;
  TEX.push(te);MAT.push(matOf(te));matFaces.push([]);
  GLT[i]=colourTex(te.c||[0.5,0.5,0.5]);
  if(t.b!=null)TEXURL[i]=blobTexture(t.b,t.m,x=>{GLT[i]=x;},P);
  if(t.gb!=null&&LIT)blobTexture(t.gb,t.gm,x=>{GLTG[i]=x;},P);
  SIM.texi.set(t.n,i);return i;
}
// the launcher's replies
window.MOHAA_SIMMODEL=async function(path,b64){
  const p=String(path||'').toLowerCase();if(SIM.busy===p)SIM.busy='';
  try{
    if(!gl)throw new Error('no 3D view');
    const P=await decodePacket(String(b64||''));
    const M=(P.models||[])[0];if(!M)throw new Error('the build sent no model');
    const ti=(P.tex||[]).map(t=>simTexIndex(t,P));
    const M2=Object.assign({},M,{s:M.s.map(s=>{const c=s.slice();c[2]=ti[s[2]]!=null?ti[s[2]]:0;return c;})});
    if(!SIM.src)SIM.src=new Map();SIM.src.set(p,[M2,P]);         // Modify builds its own from it
    SIM.cache.set(p,modelR(M2,P));
  }catch(e){SIM.fail.set(p,String(e&&e.message||e));
    if(SIM.pick===p)flash('Simulate: '+p+' can\'t be drawn ('+(e&&e.message||e)+'): the box flies instead');}
  if(MOD.mwant&&MOD.mwant.delete(p)){if(MOD.mr)MOD.mr.delete(p);requestDraw();}
  if(SIM.pick===p)simUseModel();else simModelText();
};
window.MOHAA_SIMMODEL_FAIL=function(path,why){
  const p=String(path||'').toLowerCase();if(SIM.busy===p)SIM.busy='';
  SIM.fail.set(p,String(why||'not built'));
  if(MOD.mwant&&MOD.mwant.delete(p)){if(!MOD.mr)MOD.mr=new Map();MOD.mr.set(p,null);requestDraw();}
  if(SIM.pick===p){flash('Simulate: '+p+' can\'t be drawn ('+why+'): the box flies instead');simUseModel();}
};
window.MOHAA_SIM_MODELS=function(list,why){
  SIM.list=Array.isArray(list)?list.map(x=>String(x).toLowerCase()):null;SIM.listErr=why?String(why):'';SIM.asked=false;
  if($('simOv').style.display!=='none')simListRender();
};
// ---- the model picker ------------------------------------------------------------------------
function simOpen(){
  $('simOv').style.display='flex';stopCamera();
  if(!SIM.list&&!SIM.asked&&simPost('mohaa-sim-models'))SIM.asked=true;
  const q=$('simQ');q.value='';simListRender();setTimeout(()=>q.focus(),0);
}
function simClose(){$('simOv').style.display='none';const a=document.activeElement;if(a&&a.id==='simQ')a.blur();}
function simListRender(){
  const L=$('simList'),q=$('simQ').value.trim().toLowerCase(),terms=q.split(/\s+/).filter(Boolean);
  const ok=p=>terms.every(t=>p.includes(t));
  const own=[...new Set((D.models||[]).map(M=>String(M.p||'').toLowerCase()).filter(Boolean))].sort();
  const ownSet=new Set(own),pak=(SIM.list||[]).filter(p=>!ownSet.has(p));
  const esc=x=>x.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  let h='',n=0;const MAXR=400;
  const sect=(title,arr)=>{const m=arr.filter(ok);if(!m.length)return;h+='<div class="sh">'+title+' ('+m.length+')</div>';
    for(const p of m){if(n>=MAXR)break;n++;h+='<div class="it'+(p===SIM.pick?' on':'')+'" data-p="'+esc(p)+'" title="'+esc(p)+'">'+esc(p.replace(/^models\//,''))+'</div>';}};
  sect('Models this map places',own);
  sect('Models in the paks',pak);
  L.innerHTML=h||'<div class="sh">No model matches</div>';
  let st='';
  if(!simHost())st='In a browser only the map\'s own models can fly (the Map Viewer lists every model in the paks)';
  else if(SIM.listErr)st=SIM.listErr;
  else if(!SIM.list)st='Asking the launcher for the paks\' models…';
  if(n>=MAXR)st=(st?st+' · ':'')+'Showing the first '+MAXR+': type more to narrow it down';
  $('simStat').textContent=st;
}
function simInit(){
  if(!$('bSim'))return;
  try{SIM.pick=String(LS.get(SIM_LS)||'').toLowerCase();}catch(_e){SIM.pick='';}
  $('bSim').onclick=simStart;
  $('bSimReset').onclick=()=>simReset(false);
  $('bSimPick').onclick=simOpen;
  $('simClose').onclick=simClose;
  $('simBoxBtn').onclick=()=>simSetPick('');
  $('simOv').addEventListener('click',e=>{if(e.target===$('simOv'))simClose();});
  $('simQ').addEventListener('input',simListRender);
  $('simQ').addEventListener('keydown',e=>{
    if(e.key==='Escape'){simClose();e.preventDefault();e.stopPropagation();return;}
    if(e.key==='Enter'){const f=$('simList').querySelector('.it');if(f)simSetPick(f.dataset.p);e.preventDefault();e.stopPropagation();}});
  $('simList').addEventListener('click',e=>{const it=e.target.closest('.it');if(it)simSetPick(it.dataset.p);});
  $('simMul').onchange=()=>{const m=parseFloat($('simMul').value)||1,now=performance.now();
    if(SIM.run){const x=(now-SIM.t0)*SIM.mul;SIM.t0=now-x/m;}SIM.mul=m;$('simMul').blur();};
  // (let go of the focus, so the camera keys work again straight away)
  $('simCam').onchange=()=>{SIM.camT=0;$('simCam').blur();};
  $('simEye').onchange=()=>{SIM.camT=0;$('simEye').blur();};
  $('simZoom').oninput=simZoomShow;$('simZoom').onchange=()=>$('simZoom').blur();simZoomShow();
  simModelText();
}
// ============================================================================
//  SIMULATE ON A PATH NODE: a human with a weapon on an info_pathnode or info_waypoint
// ============================================================================
// The panel's Simulate section also shows for an info_pathnode or info_waypoint (a map's own
// or one Modify placed). Spawn stands a human of the chosen kind, holding the chosen weapon,
// on it: dropped to the floor (droptofloor, as the game does) and facing the node's yaw,
// playing his idle. A node with special spawnflags can then be Simulated: he plays the
// animation the game plays there (PathNode::GetSpecialAttack: CORNER_LEFT / CORNER_RIGHT take
// the _wall_ ones, CRATE the _crate_ ones, from anim/cornerleft.scr, cornerright.scr,
// overattack.scr; LOW_WALL_ARC, SNIPER and DUCK the aim and crouch stances), so a wall, a
// crate that is too high or a node too near a wall shows in the animation itself: nothing
// here stops him going through them. Move runs or walks him along the node's "target" chain,
// or to whatever is clicked next, routed over the AI's path nodes as the game routes him
// (below). Respawn puts him back on the node. The human and weapon are built by the launcher
// from the paks (mohaa_map_actor.py) as one packet with the human's skin weights; the page
// poses him itself, as the Model Viewer does (worldFromPose / skin), and the weapon rides his
// tag_weapon_right as a rigid model. Prefix act: nothing here is the spline Simulate's.
const ACT={n:0,lists:null,listErr:'',asked:false,built:new Map(),byK:new Map(),cur:null,want:null,msg:'',pose:0,hum:'',wpn:''};
const ACT_LS_H='mohaaMapViewerActHuman', ACT_LS_W='mohaaMapViewerActWeapon';
const ACT_KEEP=4;           // actors kept built (the launcher keeps as many)
const ACT_HOLD=0.35;        // a step shows at least this long (s)
const ACT_IDLE_DT=50;       // ms between the idle's poses
const ACT_DEF_H='models/human/german_wehrmact_soldier.tik', ACT_DEF_W='models/weapons/mp40.tik';
// the Model Viewer's skeleton maths (mohaa_view.py qmat / mmul / mvec): the quaternion is
// conjugated, as the .skc's are
function actQmat(q){const x=-q[0],y=-q[1],z=-q[2],w=q[3];return[
  1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y),
  2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x),
  2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)];}
function actMmul(A,B){const R=new Array(9);for(let i=0;i<3;i++)for(let j=0;j<3;j++){let s=0;for(let k=0;k<3;k++)s+=A[i*3+k]*B[k*3+j];R[i*3+j]=s;}return R;}
function actMvec(A,v){return[A[0]*v[0]+A[1]*v[1]+A[2]*v[2],A[3]*v[0]+A[4]*v[1]+A[5]*v[2],A[6]*v[0]+A[7]*v[1]+A[8]*v[2]];}
// each bone's world matrix and position for a pose: over[i] is a bone's [px,py,pz,qx,qy,qz,qw]
// or a rotation alone [qx,qy,qz,qw] (the clip has no "<bone> pos": the base position stays),
// every other bone has its base pose
function actWorld(sk,over){
  const NB=sk.bn.length,R=new Array(NB),T=new Array(NB),done=new Uint8Array(NB),B=sk.base;
  const res=i=>{if(done[i])return;done[i]=1;let p,q;const a=over&&over[i];
    if(a&&a.length===4){p=[B[i*7],B[i*7+1],B[i*7+2]];q=a;}
    else if(a){p=[a[0],a[1],a[2]];q=[a[3],a[4],a[5],a[6]];}
    else{p=[B[i*7],B[i*7+1],B[i*7+2]];q=[B[i*7+3],B[i*7+4],B[i*7+5],B[i*7+6]];}
    const lR=actQmat(q),par=sk.bp[i];
    if(par<0){R[i]=lR;T[i]=p;}
    else{res(par);R[i]=actMmul(R[par],lR);const pt=actMvec(R[par],p);T[i]=[pt[0]+T[par][0],pt[1]+T[par][1],pt[2]+T[par][2]];}};
  for(let i=0;i<NB;i++)res(i);
  return{R:R,T:T};
}
// every vertex of the human for a pose, in the mesh's own space (its load_scale applied:
// ModelBuilder writes the model that way), into b.out
function actSkin(b,w){
  const sk=b.sk,wc=sk.wc,wb=sk.wb,ww=sk.ww,wo=sk.wo,out=b.out,sc=b.H.M.sc||1,NB=sk.bn.length;
  let k=0;
  for(let i=0;i<wc.length;i++){let X=0,Y=0,Z=0;
    for(let n=wc[i];n>0;n--,k++){const bi=wb[k];if(bi>=NB)continue;
      const wv=ww[k],ox=wo[k*3],oy=wo[k*3+1],oz=wo[k*3+2],R=w.R[bi],T=w.T[bi];
      X+=wv*(R[0]*ox+R[1]*oy+R[2]*oz+T[0]);Y+=wv*(R[3]*ox+R[4]*oy+R[5]*oz+T[1]);Z+=wv*(R[6]*ox+R[7]*oy+R[8]*oz+T[2]);}
    out[i*3]=X*sc;out[i*3+1]=Y*sc;out[i*3+2]=Z*sc;}
}
// a pose between two frames of a clip: positions blend, rotations take the short way
function actLerp(fa,fb,u){
  if(!fb||u<=0)return fa;
  const o={};
  for(const i in fa){const a=fa[i],b=fb[i];
    if(!b||b.length!==a.length){o[i]=a;continue;}
    const r=new Array(a.length),qo=a.length-4;let d=0;
    for(let k=0;k<4;k++)d+=a[qo+k]*b[qo+k];
    const sg=d<0?-1:1;
    for(let k=0;k<qo;k++)r[k]=a[k]+(b[k]-a[k])*u;
    let l=0;for(let k=0;k<4;k++){r[qo+k]=a[qo+k]+(b[qo+k]*sg-a[qo+k])*u;l+=r[qo+k]*r[qo+k];}
    l=Math.sqrt(l)||1;for(let k=0;k<4;k++)r[qo+k]/=l;
    o[i]=r;}
  return o;
}
function actFrameAt(rec,t){
  const F=rec.frames,ft=rec.frameTime||0.05;if(!F.length)return null;
  const x=Math.max(0,t)/ft,i=Math.min(F.length-1,Math.floor(x)),j=Math.min(F.length-1,i+1);
  return actLerp(F[i],F[j],Math.min(1,x-i));
}
// a role's clips end to end: each plays at its own frame time, a short one is held to
// ACT_HOLD, the last frame stays when it ends
// A clip's server commands can move the weapon to the other hand (the right-corner clips
// hold it there: `attachtohand offhand`): r.hand is [[frame, 0 main | 1 other]], frame -1 the
// last; the hand a clip ends with is the one the next starts with, and every role starts
// with the weapon in the main hand.
function actTimeline(a){
  const segs=[];let t=0,hand=0,off=[0,0,0];
  for(const nm of a.seq){const r=a.recs[nm];if(!r||!r.frames.length)continue;
    const ft=r.frameTime||0.05,play=Math.max(0,(r.frames.length-1)*ft),len=Math.max(play,ACT_HOLD),last=r.frames.length-1;
    const ev=(r.hand||[]).map(e=>[e[0]<0?last:Math.min(last,e[0]),e[1]]).sort((x,y)=>x[0]-y[0]);
    const g={r:r,t0:t,play:play,len:len,name:nm,ev:ev,hand0:hand,o0:off.slice()};
    for(const e of ev)hand=e[1];
    // the clip's own movement (r.dl: running sum of its frame deltas, x ahead / y left) carries on
    // from where the clip before it left him
    if(r.dl&&r.dl.length>=3*(last+1)){off=[off[0]+r.dl[last*3],off[1]+r.dl[last*3+1],off[2]+r.dl[last*3+2]];}
    segs.push(g);t+=len;}
  return{segs:segs,total:t};
}
// how far a clip has moved him by its local time t, in his own space (x ahead, y left)
function actMoveAt(g,t){
  const r=g.r,o=g.o0;
  if(!r.dl)return o;
  const ft=r.frameTime||0.05,last=r.frames.length-1,x=Math.max(0,t)/ft,i=Math.min(last,Math.floor(x)),j=Math.min(last,i+1),u=Math.min(1,x-i),d=r.dl;
  return[o[0]+d[i*3]+(d[j*3]-d[i*3])*u,o[1]+d[i*3+1]+(d[j*3+1]-d[i*3+1])*u,o[2]+d[i*3+2]+(d[j*3+2]-d[i*3+2])*u];
}
// the hand the weapon is in at a clip's local time t
function actHandAt(g,t){
  const fi=t>=g.play?g.r.frames.length-1:Math.floor(Math.max(0,t)/(g.r.frameTime||0.05));
  let h=g.hand0;for(const e of g.ev)if(e[0]<=fi)h=e[1];
  return h;
}
// the pose and the weapon's hand at time t into a role: {p, h}
function actPoseAt(tl,t){
  if(!tl.segs.length)return null;
  let s=tl.segs[tl.segs.length-1];
  for(const g of tl.segs)if(t<g.t0+g.len){s=g;break;}
  const lt=Math.min(s.play,t-s.t0);
  return{p:actFrameAt(s.r,lt),h:actHandAt(s,t-s.t0),m:actMoveAt(s,lt)};
}
// ---- the node ------------------------------------------------------------------------------
// One selected entity as a node he can stand on (ACT_CLS), from Modify's entity m or the map's
// entity ei: its key, kvl, origin (as the map has it: not dropped), yaw and spawnflags; null
// when it isn't such a node
function actItem(m,ei){
  let key,kvl,cls='';
  if(m&&!modIsMap(m)){
    if(!ACT_CLS.has(modCls(m)))return null;
    key='m'+m.id;kvl=simKvl(m);cls=modCls(m);
  }else{
    if(!(ei>0)||ei>=MAP.ents.length)return null;
    const mm=MOD.ents.find(x=>x.ei===ei),ed=!!mm&&modEdited(mm);
    cls=ed?modCls(mm):String(MAP.ents[ei].kvl.classname||'').toLowerCase();
    if(!ACT_CLS.has(cls))return null;
    key='e'+ei;kvl=ed?simKvl(mm):MAP.ents[ei].kvl;
  }
  const o=parseVec(kvl.origin,3)||(ei>0&&ENTS[ei]&&ENTS[ei].origin)||[0,0,0];
  // his facing: the node's own angle; else toward its target; else null (the camera's, from
  // the moment he spawns: actYaw)
  let yaw=null;
  if(parseVec(kvl.angles,3)||isFinite(parseFloat(kvl.angle)))yaw=entAngles(kvl)[1];
  else if(kvl.target){const nx=actNamed(kvl.target);
    if(nx&&Math.hypot(nx.o[0]-o[0],nx.o[1]-o[1])>0.01)yaw=Math.atan2(nx.o[1]-o[1],nx.o[0]-o[0])*180/Math.PI;}
  return{key:key,kvl:kvl,o:o.slice(),yaw:yaw,hasAng:yaw!=null,sf:parseInt(kvl.spawnflags,10)|0,cls:cls,ei:ei};
}
// Everything selected, each entity once (a map entity selected in Modify is also in SEL):
// {n: how many things, items: the nodes among them (null for one that isn't), prims}
function selAll(){
  const seen=new Set(),items=[];let bad=false;
  const add=(k,m,ei)=>{if(seen.has(k))return;seen.add(k);const it=actItem(m,ei);if(it)items.push(it);else bad=true;};
  const ml=[];if(MOD.sel>=0&&MOD.ents[MOD.sel])ml.push(MOD.ents[MOD.sel]);for(const m of MOD.multi)ml.push(m);
  for(const m of ml)add(modIsMap(m)?'e'+m.ei:'m'+m.id,m,m.ei);
  for(const k of SEL)if(k[0]==='e')add(k,null,+k.slice(1));else{seen.add(k);bad=true;}
  return{n:seen.size,items:items,bad:bad};
}
// The node Simulate works on. One node selected: it. Several: only when they are all nodes
// and join each other directly (a node's "target" names another selected one, so the selection
// is one unbroken stretch of a path; which is also every node of a path selected): then the
// first of them along the path. Two random nodes of a path, or anything else with them: null.
function actFocus(){
  if(!MAP)return null;
  const s=selAll();
  if(!s.n)return null;
  if(s.n===1)return s.items[0]||null;
  if(s.bad||s.items.length!==s.n)return null;
  const L=s.items,by=new Map();
  L.forEach((it,i)=>{const t=it.kvl.targetname;if(t){let a=by.get(t);if(!a)by.set(t,a=[]);a.push(i);}});
  const adj=L.map(()=>[]),hasIn=L.map(()=>false);
  L.forEach((it,i)=>{const t=it.kvl.target;if(!t)return;
    for(const j of by.get(t)||[]){if(j===i)continue;adj[i].push(j);adj[j].push(i);hasIn[j]=true;}});
  const seen=new Set([0]),q=[0];
  while(q.length){const i=q.pop();for(const j of adj[i])if(!seen.has(j)){seen.add(j);q.push(j);}}
  if(seen.size!==L.length)return null;
  let h=hasIn.indexOf(false);if(h<0)h=0;      // a loop has no first: the first selected
  return L[h];
}
// the classes he can stand on: path nodes (with their animations) and waypoints (to run from)
const ACT_CLS=new Set(['info_pathnode','info_waypoint']);
// What the node's spawnflags make the man do: {role, note}. The special attacks in the order
// PathNode::GetSpecialAttack tests them (CORNER_LEFT, CORNER_RIGHT, CRATE); a combination the
// AI refuses (IsValidPathnode: nodeFlagsBad) has no role. Same as flags_role in mohaa_map_actor.py.
const ACT_FLAGS=[[2,'DUCK'],[4,'COVER'],[8,'CONCEALMENT'],[16,'CORNER_LEFT'],[32,'CORNER_RIGHT'],[64,'SNIPER'],[128,'CRATE']];
function actRole(sf,cls){
  if(cls==='info_waypoint')return{role:null,note:'A waypoint has no node animation: he can run or walk from it.'};
  const v=sf&0xfe;
  if(!v&&!(sf&256))return{role:null,note:'No spawnflags: he only stands on the node.'};
  const nm=ACT_FLAGS.filter(x=>v&x[0]).map(x=>x[1]);if(sf&256)nm.push('LOW_WALL_ARC');
  const names=nm.join(' + ');
  if(nodeFlagsBad(sf))return{role:null,note:names+': the AI can\'t combine these flags (the game draws the node black), so there is nothing to play'};
  if(v&16)return{role:'left',note:'CORNER_LEFT'};
  if(v&32)return{role:'right',note:'CORNER_RIGHT'};
  if(v&128)return{role:'crate',note:'CRATE'};
  // LOW_WALL_ARC (Spearhead / Breakthrough): anim/lowwall.scr with DUCK, else highwall.scr
  if(sf&256)return{role:(v&2)?'lowwall':'highwall',note:'LOW_WALL_ARC'+((v&2)?' + DUCK':'')+' (Spearhead / Breakthrough)'};
  if(v&64)return{role:'sniper',note:'SNIPER'};
  if(v&2)return{role:'duck',note:'DUCK'};
  return{role:null,note:names+' has no special animation: he only stands on the node'};
}
// the node dropped to the floor (droptofloor), where his feet are
// his yaw on the node: the node's (angle or target), else the camera's yaw when he spawned
function actYaw(f,c){return f.yaw!=null?f.yaw:(c&&c.camYaw!=null?c.camYaw:0);}
function actPlace(f){
  let o=f.o;
  try{o=pgDrop(f.o);ACT.dropWarn=false;}
  catch(e){if(!ACT.dropWarn){ACT.dropWarn=true;flash('Simulate: the node can\'t be dropped to the floor ('+(e&&e.message||e)+'): he stands on it where it is');}}
  return o;
}
// ---- the lists and the picks ------------------------------------------------------------------
function actLabel(p){return p.replace(/^models\/(human|weapons)\//,'').replace(/\.tik$/,'');}
// pak names go into the lists as text: a crafted entry name must not become markup
function actEsc(x){return String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function actFill(){
  const H=$('actHum'),W=$('actWpn');if(!H||!W)return;
  const L=ACT.lists;
  if(!L){H.innerHTML='';W.innerHTML='';H.disabled=W.disabled=true;return;}
  const lh=LS.get(ACT_LS_H)||ACT.hum||ACT_DEF_H,lw=LS.get(ACT_LS_W)||ACT.wpn||ACT_DEF_W;
  H.innerHTML=L.h.map(p=>'<option value="'+actEsc(p)+'">'+actEsc(actLabel(p))+'</option>').join('');
  W.innerHTML=L.w.map(x=>'<option value="'+actEsc(x[0])+'" title="animations: '+actEsc(x[1])+'">'+actEsc(actLabel(x[0]))+' ('+actEsc(x[1])+')</option>').join('');
  H.value=L.h.includes(lh)?lh:(L.h.includes(ACT_DEF_H)?ACT_DEF_H:L.h[0]);
  W.value=L.w.some(x=>x[0]===lw)?lw:(L.w.some(x=>x[0]===ACT_DEF_W)?ACT_DEF_W:L.w[0][0]);
  ACT.hum=H.value;ACT.wpn=W.value;H.disabled=W.disabled=false;
}
window.MOHAA_SIM_ACTORS=function(h,w,why){
  ACT.asked=false;
  if(Array.isArray(h)&&Array.isArray(w)&&h.length&&w.length){
    ACT.lists={h:h.map(x=>String(x).toLowerCase()),w:w.map(x=>[String(x[0]).toLowerCase(),String(x[1])])};ACT.listErr='';}
  else{ACT.lists=null;ACT.listErr=String(why||'No actor list');}
  actFill();simPanel();
};
// ---- building ---------------------------------------------------------------------------------
function actFree(b){
  if(!b||!gl)return;
  for(const R of[b.H,b.Wp]){if(!R)continue;
    for(const k of['vbP','vbT','ib','vbE','vbN','vbA2','vbA2M','instBuf','selBuf'])if(R[k])gl.deleteBuffer(R[k]);
    if(R.vao)gl.deleteVertexArray(R.vao);if(R.vaoSel)gl.deleteVertexArray(R.vaoSel);}
  b.H=b.Wp=null;
}
function actGet(hum,wpn){
  const key=hum+'|'+wpn;let b=ACT.built.get(key);
  if(b)return b;
  b={k:'a'+(++ACT.n),key:key,hum:hum,wpn:wpn,state:'building',why:'',H:null,Wp:null,sk:null,out:null,meta:null,anims:new Map(),tag:-1};
  ACT.built.set(key,b);ACT.byK.set(b.k,b);
  while(ACT.built.size>ACT_KEEP){
    let drop=null;for(const x of ACT.built.values()){if(!(ACT.cur&&ACT.cur.b===x)&&x!==b){drop=x;break;}}
    if(!drop)break;
    ACT.built.delete(drop.key);ACT.byK.delete(drop.k);actFree(drop);}
  if(!simPost('mohaa-sim-actor\n'+JSON.stringify({k:b.k,m:hum,w:wpn}))){b.state='fail';b.why='Actors need the Map Viewer: it builds them from the paks';}
  return b;
}
window.MOHAA_SIMACTOR=async function(k,meta,b64){
  const b=ACT.byK.get(k);if(!b||b.state!=='building')return;
  try{
    if(!gl)throw new Error('no 3D view');
    const P=await decodePacket(String(b64||''));
    const ti=(P.tex||[]).map(t=>simTexIndex(t,P));
    const mk=M=>{if(!M)throw new Error('the build sent no model');return Object.assign({},M,{s:M.s.map(s=>{const c=s.slice();c[2]=ti[s[2]]!=null?ti[s[2]]:0;return c;})});};
    const HM=mk((P.models||[])[meta.mi]),WM=mk((P.models||[])[meta.wi]);
    const sk=HM.sk;if(!sk)throw new Error('the human came without skin weights');
    const prev=gl.getParameter(gl.VERTEX_ARRAY_BINDING);gl.bindVertexArray(null);
    try{b.H=modelR(HM,P);b.Wp=modelR(WM,P);}finally{gl.bindVertexArray(prev);}
    b.sk={bn:sk.bn,bp:sk.bp,base:P.f32(sk.base),wc:P.bytes(sk.wc),wb:P.u32(sk.wb),ww:P.f32(sk.ww),wo:P.f32(sk.wo)};
    const nv=b.H.pos.length/3;
    if(b.sk.wc.length!==nv)throw new Error('the skin has '+b.sk.wc.length+' vertices, the mesh '+nv);
    b.tag=b.sk.bn.indexOf(String(meta.tag||'tag_weapon_right').toLowerCase());
    b.tagL=b.sk.bn.indexOf(String(meta.tagL||'tag_weapon_left').toLowerCase());
    b.out=new Float32Array(nv*3);
    b.meta=meta;b.idleTL=meta.idle?actTimeline({seq:['idle'],recs:{idle:meta.idle}}):null;
    b.state='ready';
    if(b.tag<0)flash('Simulate: this human has no '+(meta.tag||'tag_weapon_right')+': the weapon is left out');
  }catch(e){b.state='fail';b.why=String(e&&e.message||e);actFree(b);flash('Simulate: the actor can\'t be drawn ('+b.why+')');}
  if(ACT.want===b.key)actSpawnNow();
  simPanel();requestDraw();
};
window.MOHAA_SIMACT_ANIM=function(k,role,out){
  const b=ACT.byK.get(k);if(!b)return;
  b.anims.set(role,{tl:actTimeline(out),seq:out.seq});
  if(ACT.cur&&ACT.cur.b===b&&ACT.cur.wantRole===role){const c=ACT.cur;c.wantRole='';if(c.wantGo){c.wantGo=false;actGoStart();}else actPlay(role);}
  simPanel();
};
window.MOHAA_SIMACT_FAIL=function(k,role,why){
  const b=ACT.byK.get(k);
  if(!role){if(b){b.state='fail';b.why=String(why||'not built');if(ACT.want===b.key)ACT.want=null;}}
  else if(b){if(!b.anims.has(role)&&b.meta)b.meta.roles[role]=String(why||'not built');
    if(ACT.cur&&ACT.cur.b===b)ACT.cur.wantRole='';}
  ACT.msg=String(why||'not built');flash('Simulate: '+ACT.msg);simPanel();
};
// ---- spawn and simulate -----------------------------------------------------------------------
function actSpawn(){
  const f=actFocus();if(!f){flash('Select an info_pathnode first');return;}
  if(!ACT.lists){flash('The human and weapon lists aren\'t here yet');return;}
  const hum=$('actHum').value,wpn=$('actWpn').value;
  ACT.hum=hum;ACT.wpn=wpn;LS.set(ACT_LS_H,hum);LS.set(ACT_LS_W,wpn);
  const b=actGet(hum,wpn);ACT.want=b.key;ACT.node=f.key;
  if(b.state==='ready')actSpawnNow();else if(b.state==='fail')flash('Simulate: '+b.why);
  simPanel();requestDraw();
}
function actSpawnNow(){
  const f=actFocus(),b=ACT.built.get(ACT.want||'');
  if(!f||!b||b.state!=='ready'||f.key!==ACT.node)return;
  ACT.want=null;
  ACT.cur={b:b,key:f.key,o:actPlace(f),yaw:0,camYaw:((cam.yaw+180)%360+360)%360,t0:performance.now(),play:null,wantRole:'',lastIdle:0,go:null,plan:null,moved:false,wantGo:false};
  ACT.cur.yaw=actYaw(f,ACT.cur);
  actPose(performance.now());
  simPanel();requestDraw();
}
function actSimulate(){
  const c=ACT.cur,f=actFocus();if(!c||!f){flash('Spawn him on a node first');return;}
  const r=actRole(f.sf,f.cls);
  if(!r.role){flash('Simulate: '+r.note);return;}
  const b=c.b,why=b.meta.roles[r.role];
  if(why){flash('Simulate: '+why);return;}
  if(b.anims.has(r.role)){actPlay(r.role);return;}
  c.wantRole=r.role;
  if(!simPost('mohaa-sim-actor-anim\n'+JSON.stringify({k:b.k,role:r.role}))){c.wantRole='';flash('Actors need the Map Viewer');return;}
  simPanel();
}
function actPlay(role){
  const c=ACT.cur;if(!c)return;
  const a=c.b.anims.get(role);if(!a||!a.tl.segs.length){flash('Simulate: nothing to play');return;}
  c.play={tl:a.tl,t0:performance.now(),role:role,seq:a.seq};
  actPose(performance.now());simPanel();requestDraw();
}
// ---- running and walking: along a "target" chain, or to a spot you click ------------------------
// As the game sends a man to a goal (Actor::MoveToPatrolCurrentNode): a goal that is an
// info_waypoint is walked to in a straight line (SetDest, FaceMotion: no path search, the
// physics stop him at a wall); any other goal is reached by SetPath, which is
// PathSearch::FindPath: the nearest path node to him that he can see (NearestStartNode, else just
// the nearest), the nearest to the goal that it can see (NearestEndNode, which has no fallback),
// and an A* over the nodes' links between them (links that drop further than ai_fallheight are
// left out). When that finds nothing ("Path not found": no node near enough, or the nodes aren't
// joined) the game clears the path and he stays where he is; he does not run through the walls.
// The pace is the clip's own: the movement of its frames over its length.
const ACT_SPEED={run:250,walk:100};        // units/s, only when the clip carries no movement
let ACT_CELLS=null,ACT_ADJ=null;
// PathSearch's cells (AddNode): every linked node is in the four 256-unit cells round it
function actCells(A){
  if(ACT_CELLS&&ACT_CELLS.A===A)return ACT_CELLS.m;
  const NC=c=>{let v=c+8192-128;if(v<0)v=c+8192+128-1;return Math.trunc(v)>>8;};
  const m=new Map(),add=(x,y,i)=>{if(x<0||x>=64||y<0||y>=64)return;const k=x*64+y;let l=m.get(k);if(!l)m.set(k,l=[]);if(l.length<128)l.push(i);};
  for(let i=0;i<A.n;i++){if(A.f[i]&1)continue;const x=NC(A.o[i*3]),y=NC(A.o[i*3+1]);add(x,y,i);add(x+1,y,i);add(x,y+1,i);add(x+1,y+1,i);}
  ACT_CELLS={A:A,m:m};return m;
}
// each node's links (rows of A.c: from, to, fall, p1 x y z, p2 x y z)
function actAdj(A){
  if(ACT_ADJ&&ACT_ADJ.A===A)return ACT_ADJ.l;
  const l=Array.from({length:A.n},()=>[]),C=A.c;
  for(let k=0;k<C.length;k+=9){const a=C[k]|0;if(a>=0&&a<A.n)l[a].push(k);}
  ACT_ADJ={A:A,l:l};return l;
}
// NearestNodeSetup: the nodes of his cell whose height he is within reach of (MAXS_Z 94), nearest first
function actNearest(A,pos){
  const cell=actCells(A).get(gridCoord(pos[0])*64+gridCoord(pos[1]));
  const out=[];if(!cell)return out;
  for(const i of cell){const z=A.o[i*3+2];
    if(pos[2]>z+94||pos[2]+94<z)continue;
    const dx=A.o[i*3]-pos[0],dy=A.o[i*3+1]-pos[1],dz=z-pos[2];
    out.push({i:i,d:dx*dx+dy*dy+dz*dz});}
  out.sort((a,b)=>a.d-b.d);return out;
}
// the sight trace of NearestStartNode / NearestEndNode: his box (-15 -15 0, 15 15 62) from 32 up
// to the node's own 32 up
function actSees(A,pos,i){
  try{const t=pgTrace([pos[0],pos[1],pos[2]+32],[A.o[i*3],A.o[i*3+1],A.o[i*3+2]+32],[-15,-15,0],[15,15,62],false);return t.f===1&&!t.startsolid;}
  catch(_e){return true;}
}
// PathSearch::FindPath from start to end: {ok, pts: the points he walks (start, each link's two
// ends, end), nodes: the nodes it crosses} or {ok:false, why: PathSearch::last_error}
function actFindPath(A,start,end){
  const sc=actNearest(A,start);let s0=null;
  for(const c of sc)if(actSees(A,start,c.i)){s0=c.i;break;}
  if(s0==null&&sc.length)s0=sc[0].i;
  if(s0==null)return{ok:false,why:'couldn\'t find start node'};
  let e0=null;
  for(const c of actNearest(A,end))if(actSees(A,end,c.i)){e0=c.i;break;}
  if(e0==null)return{ok:false,why:'couldn\'t find end node'};
  const adj=actAdj(A),C=A.c,O=A.o,fh=+CVARS.ai_fallheight;
  const d2=(ax,ay,bx,by)=>Math.hypot(ax-bx,ay-by);
  const gs=new Map(),par=new Map();let open=[];
  const sg=d2(O[s0*3],O[s0*3+1],start[0],start[1]);
  gs.set(s0,sg);open.push({i:s0,f:sg+d2(start[0],start[1],end[0],end[1])});
  while(open.length){
    let bi=open.length-1;for(let k=open.length-1;k>=0;k--)if(open[k].f<open[bi].f)bi=k;
    const cur=open.splice(bi,1)[0],n=cur.i;
    if(n===e0){
      const links=[];for(let x=n;par.has(x);x=C[par.get(x)]|0)links.push(par.get(x));
      links.reverse();
      const pts=[start.slice()];
      for(const k of links){pts.push([C[k+3],C[k+4],C[k+5]],[C[k+6],C[k+7],C[k+8]]);}
      pts.push(end.slice());
      return{ok:true,pts:pts,nodes:links.length+1};}
    for(const k of adj[n]){
      const to=C[k+1]|0;if(to<0||to>=A.n)continue;
      if(C[k+2]>fh)continue;
      const g=Math.trunc(d2(C[k+3],C[k+4],C[k+6],C[k+7])+gs.get(n)+1);
      if(gs.has(to)&&gs.get(to)<=g)continue;
      const h=d2(C[k+6],C[k+7],end[0],end[1]);
      gs.set(to,g);par.set(to,k);
      const oi=open.findIndex(o=>o.i===to);if(oi>=0)open.splice(oi,1);
      open.push({i:to,f:Math.trunc(g+h)});}
  }
  return{ok:false,why:'unreachable path'};
}
// the floor under a place (a node sits 16 up, a waypoint where its map put it)
function actFloor(o){try{return pgDrop(o);}catch(_e){return o.slice();}}
// an entity by targetname: Modify's (a new one, or a changed map entity) else the map's own
function actNamed(tn){
  for(const m of MOD.ents){if(m.del)continue;const kv=modKvl(m);
    if(kv.targetname===tn&&(!modIsMap(m)||modEdited(m)))return{key:'m'+m.id,kvl:kv,o:modOrigin(m),cls:modCls(m),name:modName(m)};}
  for(const ei of ENTS.tn.get(tn)||[]){const e=MAP.ents[ei];if(!e||MOD.ents.some(m=>m.ei===ei&&m.del))continue;
    const o=parseVec(e.kvl.origin,3)||(ENTS[ei]&&ENTS[ei].origin);if(!o)continue;
    return{key:'e'+ei,kvl:e.kvl,o:o.slice(),cls:String(e.cls||'').toLowerCase(),name:entName(ei)};}
  return null;
}
// the "target" chain from the node: its target, that one's target... (stops where one has none,
// names nothing, or comes back to one already in it)
function actChain(f){
  const out=[],seen=new Set([f.key]);let kvl=f.kvl;
  for(let n=0;n<512;n++){
    const t=kvl&&kvl.target;if(!t)break;
    const nx=actNamed(t);if(!nx||seen.has(nx.key))break;
    seen.add(nx.key);out.push(nx);kvl=nx.kvl;}
  return out;
}
// his route through the goals, one after the other, from where he stands: {pts, fail, nodes, straight}
function actRoute(c,goals){
  const R={pts:[c.o.slice()],fail:'',nodes:0,straight:0,legs:[]};let pos=c.o.slice();
  for(const g of goals){
    const to=actFloor(g.o);
    if(g.cls==='info_waypoint'){R.pts.push(to);R.straight++;R.legs.push({e:R.pts.length-1,straight:true});pos=to;continue;}
    const A=routesOk()?PA():null;
    if(!A){R.fail=(routesOk()?'the AI paths are still being worked out: try again in a moment':'this map has no path nodes')+' (to '+g.name+')';break;}
    const r=actFindPath(A,pos,to);
    if(!r.ok){R.fail=r.why+' (to '+g.name+')';break;}
    for(let i=1;i<r.pts.length;i++)R.pts.push(r.pts[i]);
    R.legs.push({e:R.pts.length-1,straight:false});
    R.nodes+=r.nodes;pos=to;}
  return R;
}
function actGo(role,goals,label){
  const c=ACT.cur,f=actFocus();if(!c||!f){flash('Spawn him on a node first');return;}
  if(c.go||c.wantRole)return;
  const why=c.b.meta.roles[role];if(why){flash('Simulate: '+why);return;}
  const R=actRoute(c,goals);
  c.plan={role:role,label:label,R:R,n:goals.length};
  c.play=null;
  if(R.pts.length<2){
    flash(R.fail?'Path not found: '+R.fail+'. In the game he stays where he is':'Nowhere to go');simPanel();return;}
  if(c.b.anims.has(role)){actGoStart();return;}
  c.wantRole=role;c.wantGo=true;
  if(!simPost('mohaa-sim-actor-anim\n'+JSON.stringify({k:c.b.k,role:role}))){c.wantRole='';c.wantGo=false;flash('Actors need the Map Viewer');}
  simPanel();
}
function actGoStart(){
  const c=ACT.cur;if(!c||!c.plan)return;
  const P=c.plan,a=c.b.anims.get(P.role);
  if(!a||!a.tl.segs.length){flash('Simulate: nothing to play');return;}
  const rec=a.tl.segs[0].r,ft=rec.frameTime||0.05,last=rec.frames.length-1,dur=Math.max(0.05,last*ft),sc=c.b.H.M.sc||1;
  let sp=0;if(rec.dl&&rec.dl.length>=3*(last+1))sp=Math.abs(rec.dl[last*3])*sc/dur;
  P.fallback=!(sp>1);if(P.fallback)sp=ACT_SPEED[P.role];
  P.speed=sp;
  // his whole walk, tick by tick, as the game steers it (actSimRoute)
  const now=performance.now(),pts=P.R.pts;
  if(DOORS)doorsAdvance(now);                    // the doors as they stand: the plan starts from them
  const sim=actSimRoute(P.R,sp,c.yaw,now);
  c.go={pts:pts,sim:sim,speed:sp,rec:rec,dur:dur,t0:now,tl:now,yaw:c.yaw,evi:0};
  if(sim.stuck>=0)flash('He is stopped by '+entName(sim.stuck)+': it never opens for him (a shootable, TARGETED or NOT_MONSTERS door), as in game');
  c.moved=true;c.wantRole='';c.wantGo=false;
  actPose(now);simPanel();requestDraw();
}
// His walk as the game's server runs it, in 50 ms frames (level.frametime), sampled ahead of
// time so Pause and the clock stay simple. Taken from actor.cpp / actorpath.cpp / g_mmove.cpp:
//  - he doesn't follow the path's corners: ActorPath::UpdatePos aims him at a point a "look
//    ahead" further along it (PathLookAhead: a swept area that grows 1024 a frame, to 256^2,
//    while the way is clear to that point (a 30x30x60 box trace), and shrinks when it isn't),
//    so he cuts and rounds each corner; MovePath's velocity is that direction at the clip's pace
//  - his yaw is not the path's: FaceMotion turns him to his velocity, or, when that agrees, to
//    the way he has moved over the last 375-500 ms (the four 125 ms slots of m_vOriginHistory),
//    and UpdateAngles turns him there at m_fAngleYawSpeed = 360 degrees a second
//  - a path ends when he is within 16 units (x and y) of its end; an info_waypoint leg is a
//    straight walk to it (SetDest), no look-ahead
// Not here: the walls and steps of MmoveSingle (the viewer doesn't test them), and the
// long-fall cut-off in PathLookAhead.
// ---- doors on the way (Door::SpawnTriggerField / FieldTouched / TryOpen / DoorFire, doors.cpp) ----
// A man doesn't open a door with a key: the group of doors that touch (the master's chain) has
// a field round it, the group's bounds 60 units bigger in x and y and 8 in z (no field for a door
// that has "health" or is TARGETED; none that answers only players: NOT_MONSTERS). A man whose
// box is in the field makes the master try to open (the proximity test against the master's own
// box, grown by a quarter of his speed in a second, FieldTouched), which runs the same Door::Open
// as the use key. The doors are solid to him: he runs on the spot against a shut one until it has
// swung or slid clear. While the master is opening, a man in the field is held to "speed" * 64
// units a second (the door's speed is 1 / its time: a wood door, 1 second, 64) and his path's
// look-ahead is cut short (ForceShortLookahead). The doors run on copies of the live ones (the
// same doorOpen / doorsAdvance), so what the walk plans is what then plays: actDoorFire.
// Not here: DoorBlocked (a door closing on him), and the walls: he stops at a door, he doesn't
// slide along it (the viewer tests no walls, so a slide would take him round its ends).
function actDoorSim(t0){
  if(!DOORS||!DOORS.size)return null;
  const reg=new Map(),busy=new Set(),groups=[];
  for(const[ei,d]of DOORS){
    const s=Object.assign({},d,{reg:reg,busy:busy,sim:true,mv:d.mv?Object.assign({},d.mv):null});
    reg.set(ei,s);if(s.mv||s.closeAt!=null)busy.add(s);}
  for(const[ei,s]of reg){
    if(s.kind==='script'||s.master!==ei)continue;
    const mem=s.chain.map(e=>reg.get(e)).filter(Boolean);
    if(!(s.sf&128)&&!mem.some(x=>doorNum(MAP.ents[x.ei].kvl.health)>0)){
      const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
      for(const x of mem)for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],x.o[k]+x.mins[k]);mx[k]=Math.max(mx[k],x.o[k]+x.maxs[k]);}
      groups.push({m:s,mn:[mn[0]-60,mn[1]-60,mn[2]-8],mx:[mx[0]+60,mx[1]+60,mx[2]+8],resp:!(s.sf&16)});}}
  const solid=[...reg.values()].filter(s=>s.kind!=='script');
  // his box (-15 -15 0, 15 15 h) against a door where it is now: his centre in the door's own
  // frame (turned back about its origin), grown by how far his corners reach along its axes
  const hit=(s,x,y,z,h)=>{
    if(s.state==='open'&&!s.mv&&!s.a)return false;     // a START_OPEN door left where the .map has it: open in game
    const X=doorXfAt(s,s.a),R=X.R,px=x-s.o[0]-X.t[0],py=y-s.o[1]-X.t[1],pz=z-s.o[2]-X.t[2];
    const lx=R[0]*px+R[3]*py,ly=R[1]*px+R[4]*py,ex=15*(Math.abs(R[0])+Math.abs(R[1]));
    return lx+ex>s.mins[0]&&lx-ex<s.maxs[0]&&ly+ex>s.mins[1]&&ly-ex<s.maxs[1]&&pz+h>s.mins[2]&&pz<s.maxs[2];};
  const any=(x,y,z,h)=>{for(const s of solid)if(hit(s,x,y,z,h))return s;return null;};
  const DS={ev:[],cap:Infinity,blocked:0,hold:null,
    adv(T){doorsAdvance(T,busy);},
    // one frame's move, in 3-unit steps (a door is thinner than a frame's step), stopped by a shut door
    move(x,y,z,dx,dy){
      this.hold=null;if(any(x,y,z,60))return[x+dx,y+dy];       // already in one (it closed on him): free
      const n=Math.max(1,Math.ceil(Math.hypot(dx,dy)/3)),sx=dx/n,sy=dy/n;
      for(let i=0;i<n;i++){const d=any(x+sx,y+sy,z,60);if(d){this.hold=d;break;}x+=sx;y+=sy;}
      return[x,y];},
    // after the move: the fields he is in. Returns true when he is in one (ForceShortLookahead)
    post(x,y,z,vx,vy,tick){
      const T=this.T0+(tick+1)*50;let touched=false;
      this.cap=Infinity;
      for(const g of groups){
        if(!g.resp||x+15<g.mn[0]||x-15>g.mx[0]||y+15<g.mn[1]||y-15>g.mx[1]||z+94<g.mn[2]||z>g.mx[2])continue;
        touched=true;const m=g.m;
        if(m.state==='opening')this.cap=Math.min(this.cap,64/m.secs);
        if(((m.sf&32)||(m.state!=='open'&&!(m.sf&64)))&&(m.state==='open'||m.state==='opening'))continue;
        const dist=Math.hypot(vx,vy)*0.25,c=[];
        const X=doorXfAt(m,m.a),mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
        for(let k=0;k<8;k++){const p=xfP(X,[m.o[0]+((k&1)?m.maxs[0]:m.mins[0]),m.o[1]+((k&2)?m.maxs[1]:m.mins[1]),m.o[2]+((k&4)?m.maxs[2]:m.mins[2])]);
          for(let j=0;j<3;j++){mn[j]=Math.min(mn[j],p[j]);mx[j]=Math.max(mx[j],p[j]);}}
        if(x-15>mx[0]+dist||y-15>mx[1]+dist||z>mx[2]||x+15<mn[0]-dist||y+15<mn[1]-dist||z+94<mn[2])continue;
        // TryOpen, then DoorFire
        if((m.sf&33)&&(m.state==='open'||m.state==='opening')){m.sf&=~1;doorClose(m,T);this.ev.push({tick:tick+1,ei:m.ei,close:true,p:[x,y,z]});}
        else{doorOpen(m,T,[x,y,z]);this.ev.push({tick:tick+1,ei:m.ei,close:false,p:[x,y,z]});}
        doorsAdvance(T,busy);}
      return touched;},
    // a stretch of 20 seconds against a door that nothing is moving or about to move: he stays there
    stuck(){if(this.hold){if(++this.blocked>400&&!busy.size)return true;}else this.blocked=0;return false;},
    T0:t0};
  return DS;
}
// a door event the plan made, played on the live doors at its own time
function actDoorFire(e,t){
  const m=DOORS&&DOORS.get(e.ei);if(!m)return;
  if(e.close){m.sf&=~1;doorClose(m,t);}else doorOpen(m,t,e.p);
  doorBtnRender();requestDraw();
}
function actSimRoute(R,speed,yaw0,t0){
  const DT=0.05,MAXT=12000,pts=R.pts,legs=R.legs&&R.legs.length?R.legs:[{e:pts.length-1,straight:false}];
  const DS=actDoorSim(t0||performance.now());let halt=false,la=4096;
  const px=[],py=[],pz=[],yw=[],nx=[];
  let x=pts[0][0],y=pts[0][1],z=pts[0][2],yaw=((yaw0%360)+360)%360,want=yaw,ach=true,tick=0,ch=0,vx=0,vy=0;
  const hist=[[x,y],[x,y],[x,y],[x,y]];
  const sample=k=>{px.push(x);py.push(y);pz.push(z);yw.push(yaw);nx.push(k);};
  const think=()=>{const k=Math.floor(tick*50/125)%4;if(k!==ch){ch=k;hist[k>=1?k-1:3]=[x,y];}};
  const face=()=>{
    if(vx*vx+vy*vy>1){let dx=vx,dy=vy;const h=hist[ch],ex=x-h[0],ey=y-h[1];
      if(ex*ex+ey*ey>=1&&ex*dx+ey*dy>0){dx=ex;dy=ey;}
      want=((Math.atan2(dy,dx)*180/Math.PI)%360+360)%360;ach=false;}
    if(!ach){let e=((want-yaw)%360+540)%360-180;const d=360*DT;
      if(e<-d)yaw-=d;else if(e>d)yaw+=d;else{yaw+=e;ach=true;}
      yaw=((yaw%360)+360)%360;}};
  const clear=(end)=>{try{const t=pgTrace([x,y,z+32],[end[0],end[1],end[2]+32],[-15,-15,0],[15,15,60],false);return t.f>=1&&!t.startsolid;}catch(_e){return true;}};
  sample(1);
  // one frame's step of (vx, vy): the doors run up to it, he is held to a door's opening pace
  // and stopped by a shut one; then the fields he is in (a leg's look-ahead is cut short in one)
  const apply=()=>{
    if(!DS){x+=vx*DT;y+=vy*DT;return;}
    DS.adv(DS.T0+tick*50);
    if(DS.cap<Infinity){const sp=Math.hypot(vx,vy);if(sp>DS.cap){vx*=DS.cap/sp;vy*=DS.cap/sp;}}
    const r=DS.move(x,y,z,vx*DT,vy*DT);x=r[0];y=r[1];
    if(DS.post(x,y,z,vx,vy,tick))la=4096;
    if(DS.stuck())halt=true;};
  let a=0;
  for(const leg of legs){
    const e=leg.e;if(e<=a)continue;
    if(leg.straight){
      const T=pts[e];
      while(tick<MAXT&&!halt){
        think();
        const dx=T[0]-x,dy=T[1]-y,d=Math.hypot(dx,dy),step=speed*DT;
        if(d<=step||d<1){x=T[0];y=T[1];z=T[2];vx=vy=0;tick++;sample(e);break;}
        vx=dx/d*speed;vy=dy/d*speed;apply();z+=(T[2]-z)*step/d;
        face();tick++;sample(e);}
    }else{
      const n=e-a+1,P=[];
      for(let i=0;i<n;i++)P.push({p:pts[e-i].slice(),dist:0});
      for(let i=0;i<n-1;i++)P[i].dist=Math.hypot(P[i].p[0]-P[i+1].p[0],P[i].p[1]-P[i+1].p[1]);
      let pp=n-1,chg=true,hc=false,end=[0,0,0];la=4096;
      // PathLookAhead: the point `area` along the path, as the area swept between it and him
      const look=(total)=>{
        let area=total,cp=pp,pos=P[cp].p,t=0;
        for(;;){
          if(cp===0){end=P[0].p.slice();hc=true;return area;}
          cp--;
          let nx0=P[cp].p[1]-pos[1],ny0=pos[0]-P[cp].p[0];const l=Math.hypot(nx0,ny0);if(l>0){nx0/=l;ny0/=l;}
          t=Math.abs((P[cp].p[0]-x)*nx0+(P[cp].p[1]-y)*ny0)*P[cp].dist;
          if(t>=area)break;
          area-=t;pos=P[cp].p;}
        t=area/t;const s=1-t;
        end=[pos[0]*s+P[cp].p[0]*t,pos[1]*s+P[cp].p[1]*t,pos[2]*s+P[cp].p[2]*t];hc=false;return 0;};
      while(tick<MAXT&&!halt){
        think();
        // ActorPath::UpdatePos
        let dx,dy;
        if(pp===0){end=P[0].p.slice();chg=true;hc=true;dx=end[0]-x;dy=end[1]-y;}
        else{
          if(look(la)>la-4096||clear(end)){la+=1024;if(la>65536)la=65536;chg=true;}
          else{if(chg){la-=2048;chg=false;}else la/=2;if(la<4096)la=4096;look(la);}
          dx=end[0]-x;dy=end[1]-y;}
        const dl=Math.hypot(dx,dy),ux=dl>1e-9?dx/dl:0,uy=dl>1e-9?dy/dl:0;
        let cp=pp,prev=0,cur=0;
        for(;cp>=0;cp--){cur=(P[cp].p[0]-x)*ux+(P[cp].p[1]-y)*uy;if(cur>=0)break;prev=cur;}
        if(cp<0){pp=0;}
        else if(cp!==pp){pp=cp+1;const tt=prev/(prev-cur),s=1-tt;
          for(let k=0;k<3;k++)P[pp].p[k]=P[pp].p[k]*s+P[cp].p[k]*tt;
          P[cp].dist*=s;}
        // Complete
        if(hc&&Math.abs(x-P[0].p[0])<16&&Math.abs(y-P[0].p[1])<16){vx=vy=0;break;}
        vx=ux*speed;vy=uy*speed;apply();
        // height: along the segment he is on
        const i0=Math.min(pp,n-2);
        if(i0>=0){const A=P[i0+1].p,B=P[i0].p,sx=B[0]-A[0],sy=B[1]-A[1],sl=sx*sx+sy*sy,
          uu=sl>1e-9?Math.max(0,Math.min(1,((x-A[0])*sx+(y-A[1])*sy)/sl)):1;z=A[2]+(B[2]-A[2])*uu;}
        face();tick++;sample(Math.max(a+1,e-pp));}
    }
    a=e;if(halt)break;
  }
  return{n:px.length,DT:DT,px:px,py:py,pz:pz,yw:yw,nx:nx,ev:DS?DS.ev:[],stuck:halt&&DS&&DS.hold?DS.hold.ei:-1};
}
// Run to / Walk to: the next click picks the goal (a node, any entity, or a spot)
function actPickStart(role){
  if(!ACT.cur||ACT.cur.go)return;
  if(ACT.pick&&ACT.pick.role===role){actPickCancel();return;}
  ACT.pick={role:role};
  flash((role==='run'?'Run':'Walk')+' to: click a node, an entity or a spot on the map (Esc cancels)');
  simPanel();
}
function actPickCancel(){if(!ACT.pick)return;ACT.pick=null;simPanel();flash('Cancelled');}
function actPickClick(x,y){
  const P=ACT.pick;if(!P)return false;
  let g=null;
  const mi=modPick(x,y);
  if(mi>=0){const m=MOD.ents[mi];g={o:modOrigin(m),cls:modCls(m),name:modName(m)};}
  else{
    const h=hitInfo(pickAt(x,y),x,y);
    if(h&&h.ent>0&&!isWorldlike(h.ent)){
      const e=MAP.ents[h.ent],X=ENTS[h.ent],o=parseVec(e.kvl.origin,3)||(X&&(X.origin||X.anchor));
      if(o)g={o:o.slice(),cls:String(e.cls||'').toLowerCase(),name:entName(h.ent)};}
    if(!g&&h&&h.point)g={o:h.point.slice(),cls:'',name:'the spot you clicked'};}
  if(!g){flash('Click an entity or a spot on the map (Esc cancels)');return true;}
  ACT.pick=null;
  actGo(P.role,[g],g.name);
  return true;
}
// ---- drawing --------------------------------------------------------------------------------
// light the grid gives at a place, as simInst takes it
function actLight(p){
  const G=lightGrid();let c=[255,255,255];
  if(G){const v=lgFast(G,p).slice(0,3).map(x=>x*2),m=Math.max(v[0],v[1],v[2]);c=m>255?v.map(x=>x*255/m):v;}
  return c;
}
// one instance of R: M turns its space into the world's (3x3, rows), p is where it sits
function actInst(R,M,p,c){
  const d=new Float32Array([M[0],M[1],M[2],p[0], M[3],M[4],M[5],p[1], M[6],M[7],M[8],p[2],
    0, c[0]/255,c[1]/255,c[2]/255, -1, -1, 0]);
  gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,d,gl.DYNAMIC_DRAW);R.n=1;
}
// the actor's pose now: bones from the playing clip (else the idle), the mesh skinned, the
// weapon on his hand, both placed on the node
function actPose(now){
  const c=ACT.cur;if(!c||!gl)return false;
  const b=c.b;if(b.state!=='ready'||!b.H||!b.Wp)return false;
  if(c.pauseAt!=null)now=c.pauseAt;           // Pause: the clock stands still
  let over=null,running=false,hand=0,mv=[0,0,0],pos=c.o,yaw=c.yaw;
  if(c.go){
    const g=c.go,S=g.sim,t=Math.max(0,(now-g.t0)/1000),f=Math.min(S.n-1,t/S.DT),i=Math.floor(f),j=Math.min(S.n-1,i+1),u=f-i;
    g.tl=now;
    while(g.evi<S.ev.length&&S.ev[g.evi].tick<=i){const e=S.ev[g.evi++];actDoorFire(e,g.t0+e.tick*S.DT*1000);}   // the doors he opens, at their frame
    pos=[S.px[i]+(S.px[j]-S.px[i])*u,S.py[i]+(S.py[j]-S.py[i])*u,S.pz[i]+(S.pz[j]-S.pz[i])*u];
    yaw=lerpAng(S.yw[i],S.yw[j],u);g.yaw=yaw;
    over=actFrameAt(g.rec,t%g.dur);running=true;g.cur=pos;g.nxt=S.nx[i];
    if(f>=S.n-1){c.o=pos;c.yaw=yaw;c.go=null;c.t0=now;simPanel();return actPose(now);}   // arrived: he idles there
  }else if(c.play){
    const t=(now-c.play.t0)/1000,pa=actPoseAt(c.play.tl,t);
    if(pa){over=pa.p;hand=pa.h;mv=pa.m;}
    running=t<c.play.tl.total;
    if(!running&&c.play.done!==true){c.play.done=true;simPanel();}
  }else if(b.idleTL&&b.meta.idle){
    over=actFrameAt(b.meta.idle,((now-c.t0)/1000)%Math.max(0.05,(b.meta.idle.frames.length-1)*(b.meta.idle.frameTime||0.05)));
  }
  const w=actWorld(b.sk,over);
  actSkin(b,w);
  gl.bindBuffer(gl.ARRAY_BUFFER,b.H.vbP);gl.bufferSubData(gl.ARRAY_BUFFER,0,b.out);
  const ax=anglesAxis([0,yaw,0]),Rn=[ax[0][0],ax[1][0],ax[2][0], ax[0][1],ax[1][1],ax[2][1], ax[0][2],ax[1][2],ax[2][2]];
  // the node moved by what the clip has stepped him (turned to his yaw): he leans out round the corner
  const hs0=b.H.M.sc||1,mw=actMvec(Rn,[mv[0]*hs0,mv[1]*hs0,mv[2]*hs0]),po=[pos[0]+mw[0],pos[1]+mw[1],pos[2]+mw[2]];
  c.at=po.slice();c.cyaw=yaw;                 // where he is now: Fly to and Follow go there
  const lt=actLight(po);
  actInst(b.H,Rn,po,lt);
  const tg=(hand&&b.tagL>=0)?b.tagL:b.tag;
  if(tg>=0){
    // the weapon: its mesh is in its own space, scaled by its own load_scale; the tag's
    // matrix (the main hand's, or the other's while a clip has it there) turns it into the
    // human's space and the tag's position (the human's scale applied) places it.
    // ATT_BASE_ANG of the Model Viewer's attachments is the identity.
    const hs=b.H.M.sc||1,tp=actMvec(Rn,[w.T[tg][0]*hs,w.T[tg][1]*hs,w.T[tg][2]*hs]);
    actInst(b.Wp,actMmul(Rn,w.R[tg]),[po[0]+tp[0],po[1]+tp[1],po[2]+tp[2]],lt);
  }else b.Wp.n=0;
  return running||!c.play;
}
// each frame: true when the picture changed (the idle's pose every ACT_IDLE_DT ms)
function actTick(now){
  const c=ACT.cur;if(!c)return false;
  const r=actTick2(now,c);
  if(ACT.follow&&c.at){actFollowCam(c);return true;}   // after his pose, so the camera has his latest spot
  return r;
}
// Pause: stop his clocks at this moment; Resume moves every start time on by the pause
function actPause(){
  const c=ACT.cur;if(!c)return;
  const now=performance.now();
  if(c.pauseAt==null){c.pauseAt=now;ACT.pick=null;}
  else{const d=now-c.pauseAt;c.pauseAt=null;
    if(c.go){c.go.t0+=d;c.go.tl+=d;}
    if(c.play)c.play.t0+=d;
    c.t0+=d;}
  simPanel();requestDraw();
}
// Follow: the game's third-person view (CG_OffsetThirdPersonView): the eye at his head (the
// origin + the 82 standing view height), 18 up (cg_cameraheight), back 120 (cg_cameradist)
// along the view angles, 2 down (cg_cameraverticaldisplacement), the camera a 10-unit box
// traced from his head so a wall keeps it out; when that leaves it under 40 units from his
// head (up against a wall) the pitch is cranked up 2 degrees at a time until it is 40 away,
// so it ends up over him. He looks level, along his heading.
function actCamCalc(p,yaw){
  const H=[p[0],p[1],p[2]+82],ref=[H[0],H[1],H[2]+18],mn=[-5,-5,-5],mx=[5,5,5];
  const place=a=>{const f=anglesAxis([a[0],a[1],0])[0],n=[ref[0]-120*f[0],ref[1]-120*f[1],ref[2]-120*f[2]-2];
    try{const t=pgTrace(H,n,mn,mx,false);return t.startsolid&&t.allsolid?H.slice():t.end.slice();}catch(_e){return n;}};
  const dl=q=>{const d=[q[0]-H[0],q[1]-H[1],q[2]-H[2]];return d;};
  let ang=[0,yaw],pos=place(ang),d=dl(pos);
  if(d[2]<40)d[2]=0;
  if(Math.hypot(d[0],d[1],d[2])<40){
    const orig=ang.slice();
    while(ang[0]<90){ang[0]+=2;pos=place(ang);d=dl(pos);if(d[2]<0)d[2]=0;
      if(Math.hypot(d[0],d[1],d[2])>=40){ang[0]=0.25*ang[0]+0.75*orig[0];break;}}
    if(ang[0]>90)ang[0]=orig[0];}
  return{pos:pos,pitch:ang[0],yaw:ang[1]};
}
function actFollowCam(c){
  const v=actCamCalc(c.at,c.cyaw!=null?c.cyaw:c.yaw);
  flyAnim=null;cam.pos=v.pos;cam.yaw=((v.yaw%360)+360)%360;cam.pitch=v.pitch;cam.roll=0;camChanged();
}
function actTick2(now,c){
  if(c.pauseAt!=null)return false;
  if(c.go){actPose(now);return true;}
  if(c.play&&c.play.done!==true){actPose(now);return true;}
  if(now-c.lastIdle<ACT_IDLE_DT)return false;
  c.lastIdle=now;
  if(c.play){return false;}                  // finished: the last frame stays until Reset
  return actPose(now);
}
function actDrawn(){
  const c=ACT.cur;if(!c||!c.b.H)return null;
  return c.b.Wp&&c.b.Wp.n?[c.b.H,c.b.Wp]:[c.b.H];
}
// ---- the panel ------------------------------------------------------------------------------
function actPanel(f){
  const host=simHost(),c=ACT.cur;
  if(host&&!ACT.lists&&!ACT.asked){ACT.asked=true;if(!simPost('mohaa-sim-actors'))ACT.asked=false;}
  // a different node (or none) than the actor's: he goes
  if(c&&(!f||f.key!==c.key)){ACT.cur=null;ACT.want=null;ACT.pick=null;ACT.follow=false;
    for(const b of ACT.built.values()){if(b.H)b.H.n=0;if(b.Wp)b.Wp.n=0;}requestDraw();}
  const cc=ACT.cur,r=f?actRole(f.sf,f.cls):{role:null,note:''};
  if(cc&&f&&!cc.go&&!cc.moved){cc.o=actPlace(f);cc.yaw=actYaw(f,cc);}   // the node moved: so does he (until he runs)
  const b=cc&&cc.b,busyW=ACT.want&&ACT.built.get(ACT.want),building=!!busyW&&busyW.state==='building';
  const why=b&&r.role?b.meta.roles[r.role]:'';
  $('bActSpawn').disabled=!host||!ACT.lists||building;
  $('bActSpawn').textContent=cc?'Respawn':'Spawn';
  $('bActSim').disabled=!(cc&&r.role&&!why&&!(cc.play&&cc.play.done!==true)&&!cc.wantRole&&cc.pauseAt==null);
  // Run / Walk: along the target chain, or to the next click
  const chain=f?actChain(f):[],idle=!!cc&&!cc.go&&!cc.wantRole&&!(cc.play&&cc.play.done!==true)&&cc.pauseAt==null;
  // once he has run or walked (to the end of a path, or anywhere) the path can't be started again
  // from where he stands: it would send him back through the walls; Respawn first
  $('bActRunPath').disabled=$('bActWalkPath').disabled=!(idle&&chain.length&&!cc.moved);
  $('bActRunTo').disabled=$('bActWalkTo').disabled=!idle;
  $('bActMove').disabled=!idle;
  if(!idle)$('actMoveMenu').style.display='none';
  $('bActMove').classList.toggle('on',!!ACT.pick);
  $('bActTrace').classList.toggle('on',TRACEPATH);
  $('bActRunTo').classList.toggle('on',!!ACT.pick&&ACT.pick.role==='run');
  $('bActWalkTo').classList.toggle('on',!!ACT.pick&&ACT.pick.role==='walk');
  for(const id of['bActRunPath','bActWalkPath'])$(id).title=(id==='bActRunPath'?'Run':'Walk')+' along this node\'s "target" chain: to its target, then that one\'s, and so on'+(chain.length?' ('+chain.length+' stop'+(chain.length===1?'':'s')+')':': it has no target, so there is nothing to follow');
  $('bActFly').disabled=!cc;
  $('bActPause').disabled=!cc;$('bActPause').textContent=cc&&cc.pauseAt!=null?'Resume':'Pause';
  $('bActPause').classList.toggle('on',!!cc&&cc.pauseAt!=null);
  $('bActFollow').disabled=!cc;$('bActFollow').classList.toggle('on',!!ACT.follow&&!!cc);
  let s='';
  if(!host)s='Actors need the Map Viewer: it builds them from the paks';
  else if(ACT.listErr&&!ACT.lists)s=ACT.listErr;
  else if(!ACT.lists)s='Asking the launcher for the paks\' humans and weapons…';
  else if(building)s='Building '+actLabel(busyW.hum)+' with '+actLabel(busyW.wpn)+'…';
  else if(busyW&&busyW.state==='fail')s='Can\'t build him: '+busyW.why;
  if(f&&!s){
    s=cc?(cc.play?(cc.play.done===true?'Finished: Respawn starts again':'Playing '+cc.play.seq.join(' › ')):
      cc.wantRole?'Building the '+r.note+' animation…':'Idle on the node.'):'Spawn stands him on the node.';
    s+='\n'+r.note;
    if(cc&&cc.go)s=(cc.plan.role==='walk'?'Walking':'Running')+' to '+cc.plan.label+'…';
    else if(cc&&cc.wantRole&&cc.wantGo)s='Building the '+cc.plan.role+' animation…';
    else if(cc&&cc.moved&&cc.plan)s='Arrived at '+cc.plan.label+': Respawn puts him back on the node.';
    if(ACT.pick)s+='\nClick a node, an entity or a spot to '+ACT.pick.role+' to (Esc cancels)';
    if(cc&&cc.plan){const R=cc.plan.R;
      s+='\n'+(R.nodes?'Over '+R.nodes+' path node'+(R.nodes===1?'':'s'):'')+(R.nodes&&R.straight?' and ':'')+(R.straight?R.straight+' straight leg'+(R.straight===1?'':'s')+' to a waypoint (the game doesn\'t search for those, and a wall would stop him: the viewer doesn\'t test it).':'');
      if(cc.plan.fallback)s+='\nThis clip carries no movement, so he goes at '+ACT_SPEED[cc.plan.role]+' units a second';
      if(R.fail)s+='\nPath not found: '+R.fail+'. In the game he stays where he is (g_patherror prints it), he does not run through the walls';}
    if(why)s+='\nNo animation: '+why;
    if(r.role==='lowwall'||r.role==='highwall')s+='\nSpearhead / Breakthrough only: the original game has no such node.'+((parseFloat(f.kvl.low_wall_arc)||0)>0?' He fires within '+f.kvl.low_wall_arc+' degrees either side of the node\'s yaw':' No "low_wall_arc" key, so the arc is 0 degrees: he only fires straight ahead of the node\'s yaw');
    if(r.role&&(f.sf&(16|32|128|256))&&f.kvl.angle==null&&f.kvl.angles==null)s+=f.kvl.target&&f.yaw!=null?'\nThis node has no angle: he faces its target, whatever the wall':'\nThis node has no angle: he turns to face the camera as it was when he spawned, whatever the wall';
    if(cc&&cc.pauseAt!=null)s='Paused: Resume carries on\n'+s;
    s+='\nHe is removed when this node is deselected (Respawn starts him again).';
  }
  $('actSum').textContent=s;
}
function actInit(){
  if(!$('bActSpawn'))return;
  $('bActSpawn').onclick=actSpawn;$('bActSim').onclick=actSimulate;
  $('bActPause').onclick=actPause;
  $('bActFollow').onclick=()=>{if(!ACT.cur){flash('Spawn him first');return;}
    ACT.follow=!ACT.follow;if(ACT.follow){flyAnim=null;SIM.camT=0;}simPanel();requestDraw();
    flash(ACT.follow?'Follow on: the game\'s third-person camera (moving the camera by hand turns it off)':'Follow off');};
  // Fly to: the camera goes to him (where he is now), keeping its heading and looking at his chest
  $('bActFly').onclick=()=>{const c=ACT.cur;if(!c){flash('Spawn him first');return;}
    const p=c.at||c.o,t=[p[0],p[1],p[2]+36],a=camAxes(),D2=Math.PI/180;
    let dir=vnorm(vsub(t,cam.pos))||a.f;
    const yaw=Math.atan2(dir[1],dir[0])*180/Math.PI,pitch=-Math.asin(Math.max(-1,Math.min(1,dir[2])))*180/Math.PI;
    const f=[Math.cos(pitch*D2)*Math.cos(yaw*D2),Math.cos(pitch*D2)*Math.sin(yaw*D2),-Math.sin(pitch*D2)];
    flyTo([t[0]-f[0]*120,t[1]-f[1]*120,t[2]-f[2]*120],yaw,pitch);};
  const mm=$('actMoveMenu');
  $('bActMove').onclick=e=>{e.stopPropagation();mm.style.display=mm.style.display==='flex'?'none':'flex';};
  mm.addEventListener('click',()=>{mm.style.display='none';});
  document.addEventListener('click',e=>{if(!$('actMoveWrap').contains(e.target))mm.style.display='none';});
  const chainOf=()=>{const f=actFocus();return f&&ACT.cur&&!ACT.cur.moved?actChain(f):[];};
  $('bActRunPath').onclick=()=>{const l=chainOf();if(l.length)actGo('run',l,'the end of its target chain ('+l.length+' stop'+(l.length===1?'':'s')+')');};
  $('bActWalkPath').onclick=()=>{const l=chainOf();if(l.length)actGo('walk',l,'the end of its target chain ('+l.length+' stop'+(l.length===1?'':'s')+')');};
  $('bActRunTo').onclick=()=>actPickStart('run');$('bActWalkTo').onclick=()=>actPickStart('walk');
  const ch=()=>{const H=$('actHum'),W=$('actWpn');ACT.hum=H.value;ACT.wpn=W.value;LS.set(ACT_LS_H,H.value);LS.set(ACT_LS_W,W.value);
    H.blur();W.blur();if(ACT.cur&&actFocus())actSpawn();};
  $('bActTrace').onclick=()=>{TRACEPATH=!TRACEPATH;$('bActTrace').classList.toggle('on',TRACEPATH);requestDraw();
    flash(TRACEPATH?'Trace path on: the path he follows is drawn in blue and red':'Trace path off');};
  $('actHum').onchange=ch;$('actWpn').onchange=ch;
  ACT.hum=LS.get(ACT_LS_H)||'';ACT.wpn=LS.get(ACT_LS_W)||'';
  actFill();
}
// ---- drawing: the path's curve (while the section shows) and the box ----------------------
// ai_showpath, as PathSearch::ShowNodes draws it (navigate.cpp) while he runs a path: the whole
// way from start to end in blue, the path still to go in red (each point 32 units up, over the
// green routes that ai_showroutes draws), and in yellow the line from him to his next point
// (ai_showpath 3). The game draws it for any ai_showpath; here it shows while Trace path is on
// (TRACEPATH: on with AI routes, and it can be turned off by itself).
function actShowPath(){
  const c=ACT.cur,g=c&&c.go;
  if(!g||!TRACEPATH||!g.cur)return null;
  const up=p=>[p[0],p[1],p[2]+32],out=[],P=g.pts;
  out.push([P[0],P[P.length-1],[0,0,1,1]]);
  const me=up(g.cur);let prev=me;
  for(let i=g.nxt;i<P.length;i++){const q=up(P[i]);if(i===g.nxt)out.push([me,q,[1,1,0,1]]);out.push([prev,q,[1,0,0,1]]);prev=q;}
  return out;
}
function drawSim(vp){
  const ch=SIM.run?SIM.rc:(($('simSect')&&$('simSect').style.display!=='none')?SIM.chain:null);
  const ap=actShowPath();
  if(!gl||(!ch&&!SIM.run&&!ap))return;
  const T=[],L=[],Lx=[];
  const lin=(A,p,q,c)=>A.push(p[0],p[1],p[2],q[0],q[1],q[2],c[0],c[1],c[2],c[3],q[0],q[1],q[2],p[0],p[1],p[2],c[0],c[1],c[2],c[3]);
  if(ap)for(const[p,q,c]of ap){lin(L,p,q,c);lin(Lx,p,q,[c[0],c[1],c[2],0.3]);}
  const tri=(a,b,c,col)=>{for(const p of[a,b,c])T.push(p[0],p[1],p[2],p[0],p[1],p[2],col[0],col[1],col[2],col[3]);};
  if(ch&&ch.fr.curve.length>1){const cv=ch.fr.curve,c=[1,0.62,0.12,0.95],cx=[1,0.62,0.12,0.3];
    for(let i=1;i<cv.length;i++){lin(L,cv[i-1],cv[i],c);lin(Lx,cv[i-1],cv[i],cx);}
    // each node's spot on the curve's control polygon, and its facing (its angles)
    for(const x of ch.nodes){const f=anglesAxis(x.a)[0],o=x.o,e=[o[0]+f[0]*24,o[1]+f[1]*24,o[2]+f[2]*24];lin(L,o,e,[1,0.85,0.3,0.9]);}}
  // the placeholder: a box with a nose, until (or instead of) a model
  if(SIM.run&&SIM.cur&&!(SIM.R&&SIM.R.n)){const ax=anglesAxis(SIM.cur.a),o=SIM.cur.p;
    const at=(x,y,z)=>[o[0]+ax[0][0]*x+ax[1][0]*y+ax[2][0]*z,o[1]+ax[0][1]*x+ax[1][1]*y+ax[2][1]*z,o[2]+ax[0][2]*x+ax[1][2]*y+ax[2][2]*z];
    const hx=32,hy=16,hz=12,C=k=>at(k&1?hx:-hx,k&2?hy:-hy,k&4?hz:-hz),fc=[0.95,0.55,0.15,0.55],ec=[1,0.9,0.6,1];
    for(const q of[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]){tri(C(q[0]),C(q[1]),C(q[2]),fc);tri(C(q[0]),C(q[2]),C(q[3]),fc);}
    for(const[a,d]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]])lin(L,C(a),C(d),ec);
    // the nose: a pyramid on the front, and its top marked
    const tip=at(hx+22,0,0),nc=[1,0.3,0.15,0.85];
    for(const[a,d]of[[1,3],[3,7],[7,5],[5,1]])tri(C(a),C(d),tip,nc);
    lin(L,at(-hx,0,hz),at(hx,0,hz),ec);}
  if(!T.length&&!L.length)return;
  if(!PMODT)PMODT=compile(VS_GVL,FS_LINE);
  if(!B.simBuf){B.simBuf=gl.createBuffer();B.vSim=gvLineVAO(B.simBuf,true);gl.bindVertexArray(null);}
  gl.enable(gl.DEPTH_TEST);gl.depthMask(false);gl.disable(gl.CULL_FACE);
  gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  gvUniforms(PMODT,vp,0.0015);
  gl.bindVertexArray(B.vSim);gl.bindBuffer(gl.ARRAY_BUFFER,B.simBuf);
  // the curve faintly through walls, then as it is seen
  if(Lx.length){gl.depthFunc(gl.GREATER);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(Lx),gl.STREAM_DRAW);gl.drawArrays(gl.LINES,0,Lx.length/10);}
  gl.depthFunc(gl.LEQUAL);
  if(T.length){gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(T),gl.STREAM_DRAW);gl.drawArrays(gl.TRIANGLES,0,T.length/10);}
  if(L.length){gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(L),gl.STREAM_DRAW);gl.drawArrays(gl.LINES,0,L.length/10);}
  gl.bindVertexArray(null);gl.disable(gl.BLEND);gl.depthMask(true);
}
// ============================================================================
//  Start up
// ============================================================================
async function main(){
  try{
    setLoad('Unpacking map data…',0.05);await tick();
    D=await loadData();
    setLoad('Reading the .map…',0.15);await tick();
    D.srcText=new TextDecoder('windows-1252').decode(D.bytes(D.src));
    MAP=readMap(D.srcText);
    scriptEnts();
    spawnKeys();
    TEX=(D.tex||[]).map((t,i)=>Object.assign({},t,{i:i}));
    for(const t of TEX)TEXI.set(t.n,t);
    setLoad('Building brushes, patches and terrain…',0.3);await tick();
    SC=buildScene(MAP,texFor,null);
    NF=SC.nf;
    buildEntities();
    prepMaterials();
    prepSeeThrough();
    if(D.lit){setLoad('Lighting the game\'s polygons…',0.6);await tick();LIT=buildLit();}
    gvInit();
    doorsInit();
    expInit();
    wxInit();
    const wk=MAP.ents[0]?MAP.ents[0].kvl:{};
    FOG.far=parseFloat(wk.farplane)||0;FOG.col=parseVec(wk.farplane_color,3)||[0.5,0.5,0.5];
    setLoad('Uploading to the graphics card…',0.8);await tick();
    loadOpts();
    initGL();
    buildPanel();
    modInit();
    setTimeout(modRecoverAsk,500);
    simInit();
    actInit();
    cvarCountRender();
    loadTextures();
    resize();
    rebuildWorld();
    // camera: at the player start each time the page opens
    const s=startView();
    cam.pos=s.p.slice();cam.yaw=s.y||0;cam.pitch=s.pi||0;
    $('ttl').textContent=TITLE;
    const nb=MAP.ents.reduce((a,e)=>a+e.brushes.length,0),np=MAP.ents.reduce((a,e)=>a+e.patches.length,0),nt=MAP.ents.reduce((a,e)=>a+e.terrains.length,0);
    const K=entityKinds();
    $('stats').innerHTML=nb+' brushes · '+np+' patches · '+nt+' terrain<br>'+MAP.nMap+' entities · '+(D.models||[]).length+' models · '+TEX.length+' textures<br>'+
      '<span class="ek'+(K.real>=ENT_MAX?' over':'')+'" title="Real entities: the ones the game spawns as entities, each with an entity number (.entnum).\n\n'+esc(entLimitText(K))+'">'+K.real+' real</span> · '+
      '<span class="ek'+(K.nodes>=MAX_PATHNODES?' over':'')+'" title="Simple entities: path nodes, player starts, waypoints, vehicle points and grenade hints, which the game keeps without an entity number, and the lights, info_nulls and other editor-only entities it drops once the map is loaded.\n\n'+esc(nodeLimitText(K))+'">'+K.simple+' simple</span> · '+
      '<span class="ek" title="Static props (static_* classes): models the compiler turns into scenery the game draws without an entity.">'+K.stat+' static props</span>'+
      (D.kind==='bsp'?'<br>decompiled from the .bsp (v'+(D.bsp&&D.bsp.version)+')':'')+
      (wk.message?'<br>"'+esc(wk.message)+'"':'')+
      (D.scr?'<br><a class="scrlink" data-scr title="What the level script spawns and sets: its entities (placed, and those whose place the viewer can\'t follow), setcvar and $world lines">level script: '+scrSummary()+'</a>':'')+
      (leakHas()?'<br><a class="scrlink" data-leak title="The compiler\'s leak trail (the map\'s .lin): where the void gets in and how to fix it (Leak, P)">leak trail: the map isn\'t sealed</a>':'')+
      (MAP.errors.length?'<br><a class="errlink" data-errs title="Which blocks, where they are in the .map, and why">'+MAP.errors.length+' unreadable block'+(MAP.errors.length===1?'':'s')+' skipped</a>':'');
    $('msgLine').textContent='';      // the map's title is in the stats, above the level script's line
    setTab('cls');
    $('loading').style.display='none';
    reportMapErrors();
    updateSelPanel();
    requestAnimationFrame(loop);
    draw();
  }catch(err){console.error(err);failLoad('This map could not be shown:\n'+(err&&err.message||err));}
}
// Theme at load: the launcher's (#theme=), else one baked in at build time, else the saved choice.
readTheme();
if(window.__HOSTTHEME__==='light'||window.__HOSTTHEME__==='dark')setTheme(window.__HOSTTHEME__==='light');
else if(FORCETHEME==='light'||FORCETHEME==='dark')setTheme(FORCETHEME==='light');
else if(LS.get('mohaaViewerTheme')==='light')setTheme(true);
try{applyBackdrop(LS.get('mohaaMapViewerBg')||null,false);}catch(_e){}
try{gridLoad();}catch(_e){}
// saved slider values: this browser's copy first, then the launcher's config (which wins)
try{window.MOHAA_SLIDERS(JSON.parse(LS.get('mohaaMapViewerSliders')||'null'),false);}catch(_e){}
try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-sliders-get');setTimeout(()=>{SL_READY=true;},2500);}else SL_READY=true;}catch(_e){SL_READY=true;}
main();
</script>
</body></html>
"""
