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
 #helpCard table{border-collapse:collapse;font-size:12px}
 #helpCard td{padding:2px 12px 2px 0;vertical-align:top}
 #helpCard td:first-child{color:var(--accent);white-space:nowrap}
 #helpCard .grp td{color:var(--dim);text-transform:uppercase;font-size:10px;letter-spacing:.1em;padding-top:9px}
 #helpCard .cols{display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start}
 /* The legend (L): one column per section (path nodes, entities, brushes), each scrolling
    on its own under its heading. A narrow window stacks them. */
 #legCard{width:1180px;height:min(640px,86%);display:flex;flex-direction:column;overflow:hidden}
 #legBody{flex:1 1 auto;min-height:0;display:flex}
 #legBody .sec{flex:1 1 0;min-width:0;overflow-y:auto;font-size:12px;padding:0 10px 0 14px;border-left:1px solid var(--line)}
 #legBody .sec:first-child{border-left:none;padding-left:0}
 #legBody h4{position:sticky;top:0;z-index:1;background:var(--panel);margin:0;padding:0 0 5px;
   font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}
 #legClose{flex:none;align-self:flex-start}
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
 .li{display:flex;align-items:center;gap:6px;padding:2px 5px;border-radius:4px;cursor:pointer;white-space:nowrap}
 .li:hover,.li.hot{background:var(--btn)}
 .li .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
 .li .ct{color:var(--dim);font-size:11px}
 .li .ar{color:var(--dim);font-size:10px;width:10px;text-align:center}
 .li img{width:18px;height:18px;object-fit:cover;border-radius:2px;flex:none;image-rendering:auto}
 .li.sub{padding-left:22px;font-size:12px}
 .li.sel .nm{color:var(--accent)}
 #findIn{width:100%}
 ::-webkit-scrollbar{width:10px;height:10px}
 ::-webkit-scrollbar-thumb{background:var(--line);border-radius:5px}
 ::-webkit-scrollbar-thumb:hover{background:var(--btnhover)}
 ::-webkit-scrollbar-track{background:transparent}
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
    <button class="sm" id="infoClose" title="Close (Esc)">&#10005;</button></div>
    <div id="infoBody"></div></div>
  <div id="loading"><div id="loadMsg">Loading map&hellip;</div><div class="bar"><i id="loadBar"></i></div></div>
  <div id="helpOv" class="ov" style="display:none">
   <div class="card" id="helpCard">
    <h3>Map viewer keyboard shortcuts</h3>
    <div class="cols"><table>
     <tr class="grp"><td colspan="2">Free-look camera</td></tr>
     <tr><td>drag / wheel</td><td>look around / move forward &amp; back</td></tr>
     <tr><td>W / S</td><td>move forward / back</td></tr>
     <tr><td>A / D</td><td>strafe left / right</td></tr>
     <tr><td>Space / C</td><td>move up / down</td></tr>
     <tr><td>Q / E</td><td>tilt (roll) left / right</td></tr>
     <tr><td>Up / Down</td><td>move forward / back</td></tr>
     <tr><td>Left / Right</td><td>turn left / right</td></tr>
     <tr><td>Shift</td><td>move faster</td></tr>
     <tr class="grp"><td colspan="2">Radiant-look camera (MOHRadiant keys)</td></tr>
     <tr><td>right-drag</td><td>fly: up/down = forward/back, left/right = turn</td></tr>
     <tr><td>Up / Down</td><td>move forward / back</td></tr>
     <tr><td>Left / Right</td><td>turn left / right</td></tr>
     <tr><td>, / .</td><td>strafe left / right</td></tr>
     <tr><td>D / C</td><td>move up / down</td></tr>
     <tr><td>A / Z</td><td>look up / down</td></tr>
     <tr><td>End</td><td>level the view</td></tr>
     <tr><td>Shift / Ctrl</td><td>fast / one grid step</td></tr>
     <tr><td>PgUp / PgDn</td><td>up / down one floor</td></tr>
     <tr><td>[ / ]</td><td>cubic clip nearer / further</td></tr>
     <tr class="grp"><td colspan="2">Both cameras</td></tr>
     <tr><td>middle-drag</td><td>slide (strafe / rise)</td></tr>
     <tr><td>V</td><td>switch Free-look / Radiant-look</td></tr>
     <tr><td>R</td><td>back to the player start</td></tr>
     <tr><td>F / double-click</td><td>fly to the selection</td></tr>
     <tr><td>Ctrl+\</td><td>cubic clipping on / off</td></tr>
    </table><table>
     <tr class="grp"><td colspan="2">Selecting</td></tr>
     <tr><td>click</td><td>select a brush / entity</td></tr>
     <tr><td>Shift+click</td><td>add to / remove from the selection</td></tr>
     <tr><td>Ctrl+click</td><td>select and show more info</td></tr>
     <tr><td>Alt+click</td><td>select everything of the same kind (Same kind button)</td></tr>
     <tr><td>Ctrl+Alt+click</td><td>select the whole path through an entity: its "target" chain, before and after it (Same path button)</td></tr>
     <tr><td>Ctrl+Shift+click</td><td>the clicked face's texture info (middle-click too)</td></tr>
     <tr><td>N</td><td>more info on the selection</td></tr>
     <tr><td>Backspace</td><td>hide the selection</td></tr>
     <tr><td>Shift+H</td><td>show everything hidden</td></tr>
     <tr><td>Ctrl+F or /</td><td>find (class, targetname, key, texture)</td></tr>
     <tr><td>Esc</td><td>close a card / clear the selection / close the map</td></tr>
     <tr class="grp"><td colspan="2">Show / hide (as in MOHRadiant)</td></tr>
     <tr><td>Alt+1 &hellip; Alt+0</td><td>world &middot; entities &middot; patches &middot; translucent &middot; liquids &middot; caulk &middot; clips &middot; paths &middot; AI nodes &middot; lights</td></tr>
     <tr><td>Ctrl+D / H / M</td><td>details &middot; hints &amp; skips &middot; models</td></tr>
     <tr><td>Ctrl+R / T / P / K</td><td>terrain &middot; triggers &middot; areaportals &middot; sky</td></tr>
     <tr><td>B</td><td>Full Brightness on / off (off = the game's own lighting)</td></tr>
     <tr><td>K</td><td>Simple Sky on / off (on = MOHRadiant's tiled sky brushes, off = the game's sky)</td></tr>
     <tr><td>M</td><td>Simple models on / off (on = trees drawn as the sprite the game shows far away)</td></tr>
     <tr class="grp"><td colspan="2">Display</td></tr>
     <tr><td>1&ndash;9</td><td>Texture &middot; Shade &middot; Wire &middot; Setsizes &middot; Arrows &middot; Labels &middot; Links &middot; Fog &middot; X-ray</td></tr>
     <tr><td>L</td><td>legend: what the colours, markers and editor surfaces mean</td></tr>
     <tr><td>T</td><td>light / dark theme</td></tr>
     <tr><td>\</td><td>collapse / expand the control panel</td></tr>
     <tr><td>H or ?</td><td>show / hide this panel</td></tr>
    </table></div>
    <button id="helpClose" style="margin-top:12px" title="Close this panel (Esc)">Close</button>
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
       <button class="sm" id="bSame" title="Select everything of the same kind: same class for entities, same texture for brushes (Alt+click)">Same kind</button>
       <button class="sm" id="bPath" style="display:none" title="Select the whole path through this entity: everything its &quot;target&quot; leads to and everything that leads to it (Ctrl+Alt+click)">Same path</button>
       <button class="sm" id="bHide" title="Hide the selection (Backspace). Shift+H shows everything again.">Hide</button>
       <button class="sm" id="bClear" title="Clear the selection (Esc)">Clear</button>
     </div>
     <div class="row co" id="hidLine" style="display:none"><span id="hidCount"></span><button class="sm" id="bUnhide" title="Show everything you hid (Shift+H)">Show all</button></div>
   </div>
   <div class="sect">
     <h2>Camera</h2>
     <div class="row">
       <button id="bFree" class="on" style="flex:1" title="Fly camera: mouse drag looks around, WASD moves, Space/C rise/lower (V switches)">Free-look</button>
       <button id="bRad" style="flex:1" title="MOHRadiant's camera: hold the right mouse button and push the mouse to fly; arrows, comma/period, D/C and A/Z as in the editor; Shift goes faster (V switches)">Radiant-look</button>
     </div>
     <div id="camHelpFree">
       <div class="row co">mouse drag = look</div>
       <div class="row co">wheel = move</div>
       <div class="row co"><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> move</div>
       <div class="row co"><kbd>Q</kbd>/<kbd>E</kbd> tilt</div>
       <div class="row co"><kbd>Space</kbd>/<kbd>C</kbd> up/down</div>
       <div class="row co"><kbd>End</kbd> level camera</div>
       <div class="row co"><kbd>Shift</kbd> fast camera</div>
     </div>
     <div id="camHelpRad" style="display:none">
       <div class="row co">right-drag = fly (push up to go forward)</div>
       <div class="row co"><kbd>&uarr;</kbd><kbd>&darr;</kbd> move</div>
       <div class="row co"><kbd>&larr;</kbd><kbd>&rarr;</kbd> turn</div>
       <div class="row co"><kbd>,</kbd><kbd>.</kbd> strafe</div>
       <div class="row co"><kbd>D</kbd>/<kbd>C</kbd> up/down</div>
       <div class="row co"><kbd>A</kbd>/<kbd>Z</kbd> look</div>
       <div class="row co"><kbd>End</kbd> level camera</div>
       <div class="row co"><kbd>Shift</kbd> fast camera</div>
       <div class="row co"><kbd>Ctrl</kbd> grid step</div>
     </div>
     <div class="row co">&nbsp;</div>
     <div class="row co">speed <input type="range" id="speed" min="50" max="3000" step="50" value="500" title="Camera speed in units per second (hold Shift for 4x)"><span id="speedV" style="min-width:34px;text-align:right">500</span></div>
     <div class="row co">fov <input type="range" id="fov" min="60" max="150" step="1" value="90" title="Horizontal field of view in degrees (the game's default is 80)"><span id="fovV" style="min-width:34px;text-align:right">90</span></div>
     <div class="row co"><button class="sm" id="bClip" title="Cubic clipping: hide everything further than the distance on the right, as MOHRadiant does (Ctrl+\). [ and ] change the distance.">Cubic clip</button><input type="range" id="clipD" min="256" max="16384" step="128" value="4096" style="max-width:110px"><span id="clipV">4096</span></div>
     <div class="row co" style="gap:5px">
       <input type="text" id="gotoIn" placeholder="go to: x y z" style="flex:1;min-width:0" title="Type or paste a position, e.g. ( 512 -128 64 ), and press Enter">
       <button class="sm" id="bCopyCam" title="Copy the camera position as ( x y z ) for a script">Copy pos</button>
     </div>
   </div>
   <div class="sect">
     <h2>Display</h2>
     <div class="tg" id="dispBtns"></div>
     <div class="row co" style="align-items:center;margin-top:8px">backdrop
       <input type="color" id="bgcol" value="#0e1116" style="width:44px;height:22px;padding:1px;border:1px solid var(--line);border-radius:6px;background:var(--btn);cursor:pointer" title="Backdrop colour behind the map. Overrides the theme's default; remembered.">
       <button class="sm" id="bgReset" title="Return the backdrop to the theme's default colour">Default</button>
     </div>
   </div>
   <div class="sect">
     <h2>Show</h2>
     <div class="tg" style="margin-bottom:7px"><button id="bFull" title="Full Brightness (B). Off: the map lit the way the game lights it (lightmaps, vertex light). On: every texture at full brightness, as MOHRadiant shows it.">Full Brightness<span class="k">B</span></button><button id="bSimpleSky" title="Simple Sky (K). On: the sky brushes solid, their picture tiled, as MOHRadiant draws them. Off: the game's sky box and its moving clouds, drawn behind everything, so whatever is behind a sky brush shows through it as in game.">Simple Sky<span class="k">K</span></button><button id="bSimpleMod" title="Simple models (M). On: each tree that has a sprite version is drawn as that sprite alone, the way the game draws trees far away; it turns about its upright axis to face the camera. Off: the whole tree. Models with no sprite version (bushes, props) don't change.">Simple models<span class="k">M</span></button></div>
     <div class="tg" id="filtBtns"></div>
     <div class="row" style="margin-top:7px">
       <button class="sm" id="bShowAll" title="Show every group">All</button>
       <button class="sm" id="bGameView" title="Hide what the game never draws (caulk, clips, triggers, hints, origin brushes, areaportals) and the entity markers, with the game's lighting and sky (Full Brightness and Simple Sky off)">In-game look</button>
       <button class="sm" id="bEditView" title="MOHRadiant's view: everything except hints and areaportals, at full brightness with Simple Sky on">Editor look</button>
     </div>
   </div>
   <div class="sect">
     <h2>Find</h2>
     <input type="search" id="findIn" placeholder="class, targetname, key, value, texture..." title="Type to search every entity's keys and values and every texture name. Enter selects all matches; click a result to select it and fly there. (Ctrl+F or /)">
     <div class="tabs" style="margin-top:7px">
       <button id="tabFind" class="on" title="Search results">Results</button>
       <button id="tabCls" title="Every entity class in the map, like MOHRadiant's Map Info and Entities windows">Classes</button>
       <button id="tabTex" title="Every texture the map uses">Textures</button>
     </div>
     <div id="listBox"></div>
   </div>
 </div>
</div>
<script id="mapdata" type="application/octet-stream">__DATA__</script>
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
      C_PATH=1<<18, C_MODEL=1<<19, C_STATIC=1<<20, C_VIS=1<<21;
const C_ENTITIES=C_ENTBRUSH|C_POINT|C_LIGHT|C_AINODE|C_PATH|C_MODEL|C_STATIC|C_VIS;
// C_STATIC has no Show button of its own: it marks the static props, which get no label
// unless selected; Models and Entities hide them.

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
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
// Numbers the way MOHAA scripts and .map files write them: plain integers, else up to 2 decimals.
function fnum(x){if(!isFinite(x))return '0';const r=Math.round(x);if(Math.abs(x-r)<0.005)return String(r===0?0:r);
  return (Math.round(x*100)/100).toString();}
function fvec(v){return '( '+v.map(fnum).join(' ')+' )';}
function copyText(s){
  const done=()=>flash('Copied to the clipboard');
  try{if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(s).then(done,()=>fallback());return;}}catch(_e){}
  fallback();
  function fallback(){const ta=document.createElement('textarea');ta.value=s;ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(_e){}ta.remove();}
}
let _flashT=null;
function flash(msg){const h=$('hintHover');h.textContent=msg;h.style.color='var(--accent)';
  clearTimeout(_flashT);_flashT=setTimeout(()=>{h.style.color='';h.textContent='';},1600);}

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
  requestDraw();}
themeBtn.onclick=()=>setTheme(!document.documentElement.classList.contains('light'));
const bgIn=$('bgcol');
function applyBackdrop(col,save){
  if(col)document.documentElement.style.setProperty('--bg',col);else document.documentElement.style.removeProperty('--bg');
  if(save)LS.set('mohaaMapViewerBg',col||null);
  readTheme();bgIn.value=cssVar('--bg')||bgIn.value;requestDraw();}
bgIn.oninput=()=>applyBackdrop(bgIn.value,true);bgIn.onchange=bgIn.oninput;
$('bgReset').onclick=()=>applyBackdrop(null,true);

// ---- help overlay ----------------------------------------------------------------
const helpOv=$('helpOv');
function toggleHelp(force){const show=(force!==undefined)?force:(helpOv.style.display==='none');helpOv.style.display=show?'flex':'none';
  if(show)legOv.style.display='none';}
$('bHelp').onclick=()=>toggleHelp();$('helpClose').onclick=()=>toggleHelp(false);
helpOv.addEventListener('click',e=>{if(e.target===helpOv)toggleHelp(false);});
function closeViewer(){
  // In the launcher's pane the host returns to its start page; in a browser tab, just close.
  try{if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-close');return;}}catch(_e){}
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
const view={tex:true,shade:true,wire:false,ss:false,arrows:true,labels:true,links:true,fog:false,xray:true};
let hiddenMask=C_HINT|C_PORTAL;
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
      if(mi!=null&&D.models[mi]){X.model=mi;X.cat=C_MODEL|(e.cls.startsWith('static_')?C_STATIC:0);}
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
    const tn=e.kvl.targetname;if(tn){let l=tnIndex.get(tn);if(!l){l=[];tnIndex.set(tn,l);}l.push(ei);}
    ENTS.push(X);
  }
  ENTS.tn=tnIndex;
  for(const X of ENTS)X.box=entityBox(X.ei);
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
function radiantLook(X,e){
  X.standin=!radiantKnows(X.def);
  if(X.standin)X.col=RAD_STANDIN_COL.slice();
  X.ccol=X.col;X.mcol=X.col;X.mk=1;
  const lc=parseVec(e.kvl._color,3);
  if(e.cls.startsWith('info_path')&&e.kvl.targetname){X.mk=2;X.col=X.ccol.map(v=>1-v);X.why='it has a "targetname"';}
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
  const ss=parseVec(e.kvl.setsize,6);
  if(ss)return{origin:o,mins:ss.slice(0,3),maxs:ss.slice(3),how:'"setsize" key',exact:true};
  if(X.model>=0){const M=D.models[X.model];const sc=parseFloat(e.kvl.scale)||1;
    if(M.ss)return{origin:o,mins:M.ss[0],maxs:M.ss[1],how:'setsize in '+M.p.replace(/^models\//,''),exact:true};
    // the model's own size, turned with the entity
    const ax=anglesAxis(entAngles(e.kvl)), mn=[Infinity,Infinity,Infinity], mx=[-Infinity,-Infinity,-Infinity];
    for(let c=0;c<8;c++){const v=[(c&1?M.b[1]:M.b[0])[0]*sc,(c&2?M.b[1]:M.b[0])[1]*sc,(c&4?M.b[1]:M.b[0])[2]*sc];
      for(let k=0;k<3;k++){const w=ax[0][k]*v[0]+ax[1][k]*v[1]+ax[2][k]*v[2];mn[k]=Math.min(mn[k],w);mx[k]=Math.max(mx[k],w);}}
    return{origin:o,mins:mn,maxs:mx,how:'model size (no setsize in its .tik)',exact:false};}
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
layout(location=11) in vec4 aA2; layout(location=12) in vec3 aA2M;
uniform mat4 uVP; uniform int uLit; uniform highp sampler2D uStatic; uniform int uAuto2; uniform vec3 uFwd;
out vec2 vUV; out vec3 vPos; out vec4 vCol; flat out float vPick;
void main(){vec4 p=vec4(aPos,1.0);vec3 w=vec3(dot(aR0,p),dot(aR1,p),dot(aR2,p));
  if(uAuto2==1){vec4 m=vec4(aA2.xyz,1.0);
    vec3 ax=vec3(dot(aR0.xyz,aA2M),dot(aR1.xyz,aA2M),dot(aR2.xyz,aA2M)), mn=cross(ax,uFwd);
    float l=length(mn), sc=length(vec3(aR0.x,aR1.x,aR2.x));
    w=vec3(dot(aR0,m),dot(aR1,m),dot(aR2,m))+(l>1e-6?mn*(aA2.w*sc/l):vec3(0.0));}
  vec4 c=vec4(1.0);
  if(uLit==2&&aILight.w>=0.0){int k=int(aILight.w+aEng+0.5);c=vec4(texelFetch(uStatic,ivec2(k%4096,k/4096),0).rgb,1.0);}
  else if(uLit>0)c=vec4(aILight.rgb,1.0);
  vUV=aUV;vPos=w;vCol=c;vPick=aIPick;gl_Position=uVP*vec4(w,1.0);}`;
// The game's own polygons: texture x lightmap page (aLM.z >= 0), x vertex light
// (aLM.z = -1) or as it is (aLM.z = -2). uTm is the picture stage's tcMod scale
// (RB_CalcScaleTexCoords); uAg its alphaGen (tr_shade.c ComputeColors): 1 constant,
// 2 / 3 from the base s / t coordinate (RB_CalcAlphaFromTexCoords: min, max, low cap,
// high cap in uAgP), 4 vertex alpha, 5 one minus vertex alpha.
const VS_LIT=`#version 300 es
layout(location=0) in vec3 aPos; layout(location=1) in vec2 aUV; layout(location=7) in vec4 aCol; layout(location=8) in vec3 aLM;
uniform mat4 uVP; uniform vec2 uTm; uniform int uAg; uniform vec4 uAgP;
out vec2 vUV; out vec3 vPos; out vec4 vCol; out vec3 vLM; out float vA;
void main(){vUV=aUV*uTm;vPos=aPos;vCol=aCol;vLM=aLM;
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
out vec4 o;
void main(){
  if(uClip>0.0){vec3 d=abs(vPos-uEye);if(max(d.x,max(d.y,d.z))>uClip)discard;}
  vec4 t=(uUseTex==1)?texture(uTex,vUV):vec4(uFlat,1.0);
  if(uAF==1&&t.a<=0.0)discard; if(uAF==2&&t.a<0.5)discard; if(uAF==3&&t.a>=0.5)discard;
  vec3 l=vLM.z>-0.5?texture(uLM,vec3(vLM.xy,floor(vLM.z+0.5))).rgb:(vLM.z>-1.5?vCol.rgb:vec3(1.0));
  vec3 c=t.rgb*l*uTint.rgb;
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
  glcv.addEventListener('webglcontextlost',e=>{e.preventDefault();failLoad('The graphics driver reset the 3D view. Reopen the map to continue.');});
}
function colourTex(c){const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([c[0]*255|0,c[1]*255|0,c[2]*255|0,255]));return t;}
// Pictures arrive as blobs; decode them in the background and swap them in as they load.
const TEXURL=[];
function blobTexture(blob,mime,done){
  const url=URL.createObjectURL(new Blob([D.bytes(blob)],{type:mime||'image/jpeg'}));
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
}
let faceVis=null;
function faceShown(f){
  if(SC.faceCat[f]&hiddenMask)return false;
  if(hidEnt.size&&hidEnt.has(SC.faceEnt[f]))return false;
  if(hidPrim.size&&hidPrim.has(SC.facePrim[f]))return false;
  return true;
}
function entShown(ei){const X=ENTS[ei];return !(X.cat&hiddenMask)&&!hidEnt.has(ei);}
// A brush entity whose every face is filtered out (a trigger with Triggers off) loses its
// label, box and links too.
let ENTVIS=null;
function entVisible(ei){return entShown(ei)&&(!ENTS[ei].hasGeo||!ENTVIS||!!ENTVIS[ei]);}
function rebuildWorld(){
  if(!faceVis||faceVis.length!==SC.nf)faceVis=new Uint8Array(SC.nf);
  for(let f=0;f<SC.nf;f++)faceVis[f]=faceShown(f)?1:0;
  ENTVIS=new Uint8Array(MAP.ents.length);for(let f=0;f<SC.nf;f++)if(faceVis[f])ENTVIS[SC.faceEnt[f]]=1;
  const tri=new Uint32Array(Math.max(3,SC.tri.length));let n=0;
  drawOps=[];drawTrans=[];
  // Every shown face goes into the pick pass. With the game's lighting on, the faces the
  // game draws itself (LIT.rep) are left out of the picture and its own polygons drawn
  // instead, so each texture gets one run of those faces and one of the rest.
  const rep=LIT?LIT.rep:null;
  for(const ti of matOrder){
    for(const want of (rep?[1,0]:[0])){
      const start=n;
      for(const f of matFaces[ti])if(faceVis[f]&&(!rep||rep[f]===want)){const a=SC.faceI0[f],c=SC.faceIN[f];tri.set(SC.tri.subarray(a,a+c),n);n+=c;}
      if(n>start){const op={ti:ti,start:start,count:n-start,m:MAT[ti],rep:want===1,back:(TEX[ti]||{}).g==='caulk',sky:!!((TEX[ti]||{}).f&TF_SKY)};
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
    const o=X.origin, b=X.box||{mins:[-8,-8,-8],maxs:[8,8,8]}, id=NF+1+X.ei, ol=X.ol?[X.ol[0],X.ol[1],X.ol[2],1]:[0,0,0,0];
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
// game's lighting: light grid colour and the first vertex of its baked light (or -1).
const INST_FLOATS=17;
function instData(ei){
  const X=ENTS[ei], rows=instRows(X), L=D.lit, g=L&&L.el?L.el[ei]:null, st=L&&L.st?L.st[ei]:null;
  return rows.concat([NF+1+ei, g?g[0]/255:1, g?g[1]/255:1, g?g[2]/255:1, st!=null?st:-1]);
}
function initModels(){
  (D.models||[]).forEach((M,mi)=>{
    const R={M:M,pos:D.f32(M.v),uv:D.f32(M.t),idx:D.u32(M.i),inst:[],n:0,nsel:0,sprites:[]};
    // A tree's sprite version (TF_LOD) is drawn only with Simple models on (surfOn); other
    // camera-facing sprite surfaces (coronas) are drawn as billboards (drawSprites).
    R.surfs=M.s.map(s=>{const f=(TEX[s[2]]||{}).f|0, lod=!!(f&TF_LOD);
      return {first:s[0],count:s[1],ti:s[2],name:s[3],v0:s[4]|0,vn:s[5]|0,lod:lod,sprite:!lod&&!!(f&TF_SPRITE)};});
    R.hasLod=R.surfs.some(s=>s.lod);
    R.vbP=makeBuf(gl.ARRAY_BUFFER,R.pos);R.vbT=makeBuf(gl.ARRAY_BUFFER,R.uv);R.ib=makeBuf(gl.ELEMENT_ARRAY_BUFFER,R.idx);
    // each vertex's number in the engine's own order, to find its baked light
    const eng=new Float32Array(R.pos.length/3);
    for(const s of M.s)if(s.length>=7)for(let k=0;k<s[5];k++)eng[s[4]+k]=s[6]+k;
    R.vbE=makeBuf(gl.ARRAY_BUFFER,eng);
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
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,R.ib);gl.bindVertexArray(null);return v;};
    R.vao=mk(R.instBuf);R.vaoSel=mk(R.selBuf);
    for(const s of R.surfs)if(s.sprite){let c=[0,0,0],n=0,r=0;
      for(let k=s.first;k<s.first+s.count;k++){const v=R.idx[k];c[0]+=R.pos[v*3];c[1]+=R.pos[v*3+1];c[2]+=R.pos[v*3+2];n++;}
      c=c.map(x=>x/Math.max(1,n));
      for(let k=s.first;k<s.first+s.count;k++){const v=R.idx[k];r=Math.max(r,Math.hypot(R.pos[v*3]-c[0],R.pos[v*3+1]-c[1],R.pos[v*3+2]-c[2]));}
      s.c=c;s.r=r;R.sprites.push(s);}
    MODELS.push(R);
  });
  for(const X of ENTS)if(X.model>=0)MODELS[X.model].inst.push(X.ei);
}
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
    const a=[];for(const ei of R.inst)if(entShown(ei))a.push(...instData(ei));
    gl.bindBuffer(gl.ARRAY_BUFFER,R.instBuf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a.length?a:new Array(INST_FLOATS).fill(0)),gl.DYNAMIC_DRAW);
    R.n=a.length/INST_FLOATS;
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
  const units=[];          // {i0, n, ti, f, pi, ei}
  if(L.ns){
    pos.set(bp);uv.set(D.f32(L.uv));lm.set(D.f32(L.l));col.set(D.bytes(L.c));tri.set(bi);
    const s=D.i32(L.s);
    for(let k=0;k<L.ns;k++){const o=k*6, e=s[o+3], b=s[o+4], fk=s[o+5];
      const pi=b>=0?primOf.get(key(e,b)):undefined, f=(pi!=null&&fk>=0)?faceOf(pi,fk):-1;
      units.push({i0:s[o],n:s[o+1],ti:s[o+2],f:f,pi:pi!=null?pi:-1,ei:e});}
  }
  let v=nb, t=bi.length;
  const addFace=(f,ti,pi,ei,fill)=>{      // copy a .map face's geometry, with fill() for its light
    const v0=SC.faceV0[f], vn=SC.faceVN[f];
    pos.set(SC.pos.subarray(v0*3,(v0+vn)*3),v*3);uv.set(SC.uv.subarray(v0*2,(v0+vn)*2),v*2);
    for(let q=0;q<vn;q++)fill(q,v+q);
    const a=SC.faceI0[f],c=SC.faceIN[f];
    for(let q=0;q<c;q++)tri[t+q]=SC.tri[a+q]-v0+v;
    units.push({i0:t,n:c,ti:ti,f:f,pi:pi,ei:ei});v+=vn;t+=c;rep[f]=1;};
  const pl=L.pl!=null?D.f32(L.pl):null, pc=L.pc!=null?D.bytes(L.pc):null;
  for(const[r,pi,f]of pats){
    const P=SC.prims[pi], Pd=MAP.ents[P.ent].prims[P.bn].d, cnt=r[4], layer=r[2];
    if(!pl||Pd.w*Pd.h!==cnt)continue;
    const X=new Float64Array(cnt*6);
    for(let q=0;q<cnt;q++){X[q*6]=pl[(r[3]+q)*2];X[q*6+1]=pl[(r[3]+q)*2+1];
      for(let k=0;k<4;k++)X[q*6+2+k]=pc[(r[3]+q)*4+k];}
    const g=tessPatch(Pd,X,6);
    if(!g||g.cols*g.rows!==SC.faceVN[f])continue;
    addFace(f,SC.faceTex[f],pi,P.ent,(q,o)=>{
      lm[o*3]=g.x[q*6];lm[o*3+1]=g.x[q*6+1];lm[o*3+2]=layer;
      for(let k=0;k<4;k++)col[o*4+k]=Math.max(0,Math.min(255,Math.round(g.x[q*6+2+k])));});
  }
  for(const[r,pi,f]of ters){
    const P=SC.prims[pi], org=MAP.ents[P.ent].prims[P.bn].d.org;
    addFace(f,SC.faceTex[f],pi,P.ent,(q,o)=>{
      const i=(pos[o*3]-org[0])/64, j=(pos[o*3+1]-org[1])/64;
      lm[o*3]=r[2]+i*r[4];lm[o*3+1]=r[3]+j*r[4];lm[o*3+2]=r[1];
      col[o*4]=col[o*4+1]=col[o*4+2]=col[o*4+3]=255;});
  }
  const byTex=new Map();
  units.forEach((u,k)=>{if(!u.n)return;let l=byTex.get(u.ti);if(!l){l=[];byTex.set(u.ti,l);}l.push(k);});
  return {nv:v,pos:pos.subarray(0,v*3),uv:uv.subarray(0,v*2),lm:lm.subarray(0,v*3),col:col.subarray(0,v*4),
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
  // lightmap pages: white until the picture is decoded
  B.lmTex=arrayTex(1,1,1,new Uint8Array([255,255,255,255]));
  if(L.lm!=null){const url=URL.createObjectURL(new Blob([D.bytes(L.lm)],{type:'image/png'})),im=new Image();
    im.onload=()=>{try{
      const cv=document.createElement('canvas');cv.width=im.width;cv.height=im.height;const c2=cv.getContext('2d');c2.drawImage(im,0,0);
      const px=c2.getImageData(0,0,im.width,im.height).data, S=128, n=L.nlm, cols=L.cols, out=new Uint8Array(S*S*4*n);
      for(let k=0;k<n;k++){const ox=(k%cols)*S, oy=Math.floor(k/cols)*S;
        for(let y=0;y<S;y++)out.set(px.subarray(((oy+y)*im.width+ox)*4,((oy+y)*im.width+ox+S)*4),(k*S*S+y*S)*4);}
      const t=arrayTex(S,S,n,out);gl.deleteTexture(B.lmTex);B.lmTex=t;requestDraw();
    }catch(e){console.warn('lightmaps',e);}URL.revokeObjectURL(url);};
    im.src=url;}
  // baked light of the static props, one texel per vertex, 4096 across
  if(L.sm!=null&&L.smn){const W2=4096,H2=Math.ceil(L.smn/W2),src=D.bytes(L.sm),data=new Uint8Array(W2*H2*3);data.set(src.subarray(0,Math.min(src.length,data.length)));
    B.smTex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,B.smTex);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB8,W2,H2,0,gl.RGB,gl.UNSIGNED_BYTE,data);gl.pixelStorei(gl.UNPACK_ALIGNMENT,4);
    for(const p of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,p,gl.NEAREST);}
  else B.smTex=colourTex([1,1,1]);
}
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
function cloudsMoving(){return CLOUDS_MOVE&&!simpleSky&&!(hiddenMask&C_SKY)&&!(view.fog&&FOG.far>0);}
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
  for(const[ti,list]of LIT.byTex){
    const start=n;
    for(const k of list){const u=LIT.units[k];if(!litUnitShown(u))continue;tri.set(LIT.tri.subarray(u.i0,u.i0+u.n),n);n+=u.n;}
    if(n===start)continue;
    const te=TEX[ti]||{f:0}, m=(MAT[ti]&&MAT[ti].lit)||{kind:0,af:0,alpha:1}, op={ti:ti,start:start,count:n-start,m:m};
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
  if(view.fog&&FOG.far>0)far=FOG.far*1.02;
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
let _drawReq=false;
function requestDraw(){if(_drawReq||!gl)return;_drawReq=true;requestAnimationFrame(()=>{_drawReq=false;draw();});}
function resize(){const r=glcv.getBoundingClientRect();W=Math.max(1,r.width);H=Math.max(1,r.height);DPR=Math.min(2,window.devicePixelRatio||1);
  glcv.width=Math.round(W*DPR);glcv.height=Math.round(H*DPR);cv2.width=Math.round(W*DPR);cv2.height=Math.round(H*DPR);
  ctx.setTransform(DPR,0,0,DPR,0,0);requestDraw();}
window.addEventListener('resize',resize);

function setCommon(p,vp,mode){
  gl.useProgram(p);gl.uniformMatrix4fv(p.u.uVP,false,vp);gl.uniform1i(p.u.uMode,mode);
  gl.uniform1f(p.u.uShade,view.shade?1:0);gl.uniform3fv(p.u.uEye,cam.pos);gl.uniform1f(p.u.uClip,clipOn?clipDist:0);
  gl.uniform3fv(p.u.uFogCol,FOG.col);gl.uniform3f(p.u.uFog,FOG.far*0.25,FOG.far,(view.fog&&FOG.far>0&&mode===0)?1:0);
  gl.uniform4f(p.u.uTint,1,1,1,1);gl.uniform1i(p.u.uAF,0);gl.uniform1i(p.u.uUseTex,1);gl.uniform1i(p.u.uTex,0);
  if(p.u.uPush)gl.uniform1f(p.u.uPush,0);
  if(p.u.uTm){gl.uniform2f(p.u.uTm,1,1);gl.uniform1i(p.u.uAg,0);}
  gl.activeTexture(gl.TEXTURE0);
}
// game: drawing the game's own polygons (its picture and material where they differ)
function bindMat(p,ti,mode,game){
  const m=(game&&MAT[ti]?MAT[ti].lit:MAT[ti])||{kind:0,af:0,alpha:1}, te=TEX[ti]||{c:[0.5,0.5,0.5]};
  gl.bindTexture(gl.TEXTURE_2D,(game&&GLTG[ti])||GLT[ti]||whiteTex);
  gl.uniform1i(p.u.uUseTex,(view.tex||mode===1)?1:0);
  gl.uniform3fv(p.u.uFlat,te.c||[0.5,0.5,0.5]);
  gl.uniform1i(p.u.uAF,m.af&&(view.tex||mode===1)?m.af:0);
  if(mode===0)gl.uniform4f(p.u.uTint,1,1,1,m.kind===4?m.alpha:1);
  if(m.two||mode===1)gl.disable(gl.CULL_FACE);else gl.enable(gl.CULL_FACE);
  if(game&&p.u.uTm){const tm=m.tm||[1,1],q=m.agp||[1,0,0,1];
    gl.uniform2f(p.u.uTm,tm[0],tm[1]);gl.uniform1i(p.u.uAg,m.agk|0);gl.uniform4f(p.u.uAgP,q[0],q[1],q[2],q[3]);}
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
  gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D_ARRAY,B.lmTex);gl.activeTexture(gl.TEXTURE0);
  gl.uniform1i(p.u.uLM,1);
}
function setModelCommon(vp,mode,lit){
  setCommon(PM,vp,mode);
  gl.activeTexture(gl.TEXTURE3);gl.bindTexture(gl.TEXTURE_2D,B.smTex||whiteTex);gl.activeTexture(gl.TEXTURE0);
  gl.uniform1i(PM.u.uStatic,3);gl.uniform1i(PM.u.uLit,0);
  gl.uniform1i(PM.u.uAuto2,0);gl.uniform3fv(PM.u.uFwd,camAxes().f);
  if(lit)gl.uniform1f(PM.u.uShade,0);
}
function drawScene(vp,mode){
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);gl.frontFace(gl.CW);gl.cullFace(gl.BACK);
  if(mode===2){   // pick ids of the sky faces alone, at their own depth (pickAt)
    setCommon(PW,vp,1);gl.bindVertexArray(B.vTri);gl.disable(gl.BLEND);
    for(const op of drawOps)if(op.sky){bindMat(PW,op.ti,1);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
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
    gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
  gl.uniform1f(PW.u.uPush,0);
  if(lit){
    setCommon(PLIT,vp,0);bindLit(PLIT);gl.bindVertexArray(B.vLit);
    for(const op of LIT.ops){bindMat(PLIT,op.ti,0,true);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
  }
  if(gameSky&&mode===0)drawGameSky(vp);
  // models (solid surfaces)
  setModelCommon(vp,mode,lit);
  for(const R of MODELS){if(!R.n)continue;gl.bindVertexArray(R.vao);
    for(const s of R.surfs){if(!surfOn(R,s))continue;const k=(MAT[s.ti]||{}).kind||0;if(mode===0&&k>=2)continue;
      if(lit)gl.uniform1i(PM.u.uLit,modelLitMode(s.ti));
      gl.uniform1i(PM.u.uAuto2,s.lod?1:0);
      bindMat(PM,s.ti,mode);gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.n);}}
  gl.uniform1i(PM.u.uAuto2,0);
  // entity markers
  if(boxCount){setCommon(PMK,vp,mode);gl.uniform1f(PMK.u.uOlW,3*DPR);
    gl.enable(gl.CULL_FACE);gl.bindVertexArray(B.vMark);gl.drawElements(gl.TRIANGLES,boxCount,gl.UNSIGNED_INT,0);}
  if(mode===1){
    // see-through world surfaces are pickable too (that is how you find a trigger)
    setCommon(PW,vp,1);gl.bindVertexArray(B.vTri);
    for(const op of drawTrans){bindMat(PW,op.ti,1);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
    // the game's sky can be picked only where nothing else is, as it is seen
    if(gameSky){gl.depthRange(1,1);
      for(const op of drawOps)if(op.sky){bindMat(PW,op.ti,1);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
      gl.depthRange(0,1);}
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
      gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
    gl.depthMask(false);
  }
  setCommon(PW,vp,0);gl.bindVertexArray(B.vTri);
  for(const op of drawTransG){if(lit&&op.rep)continue;blendFor(op.m.kind);bindMat(PW,op.ti,0);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
  setModelCommon(vp,0,lit);
  for(const R of MODELS){if(!R.n)continue;gl.bindVertexArray(R.vao);
    for(const s of R.surfs){if(!surfOn(R,s))continue;const k=(MAT[s.ti]||{}).kind||0;if(k<2)continue;
      if(lit)gl.uniform1i(PM.u.uLit,modelLitMode(s.ti));
      gl.uniform1i(PM.u.uAuto2,s.lod?1:0);
      blendFor(k);bindMat(PM,s.ti,0);gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.n);}}
  gl.uniform1i(PM.u.uAuto2,0);
  setCommon(PW,vp,0);gl.bindVertexArray(B.vTri);
  for(const op of drawTransE){if(lit&&op.rep)continue;blendFor(op.m.kind);bindMat(PW,op.ti,0);gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
  // the inner sides of see-through brushes the camera is inside
  if(insideOps.length){gl.bindVertexArray(B.vInside);
    for(const op of insideOps){blendFor(4);bindMat(PW,op.ti,0);gl.enable(gl.CULL_FACE);gl.cullFace(gl.FRONT);
      gl.drawElements(gl.TRIANGLES,op.count,gl.UNSIGNED_INT,op.start*4);}
    gl.cullFace(gl.BACK);}
  drawSprites(vp);
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
  const fogged=view.fog&&FOG.far>0, flat=fogged?FOG.col:skyColour(), T=(performance.now()-T0)/1000;
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
function drawSprites(vp){
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
  setCommon(PW,vp,0);gl.bindVertexArray(B.vSp);gl.disable(gl.CULL_FACE);
  for(const op of ops){const k=(MAT[op[0]]||{}).kind||0;blendFor(k===0?3:k);bindMat(PW,op[0],0);gl.disable(gl.CULL_FACE);gl.drawArrays(gl.TRIANGLES,op[1],op[2]);}
}
function draw(){
  if(!gl||!SC)return;
  FRAMES++;skyQueryPoll();
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  gl.viewport(0,0,glcv.width,glcv.height);
  // with the map's fog on, everything past the fog's far end is fog colour, as in game
  const bg=(view.fog&&FOG.far>0)?FOG.col:TH.bg;
  gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  VP=viewProj(null);
  updateInside(false);
  drawScene(VP,0);
  drawSelection(VP);
  drawLines(VP);
  draw2D();
  updateHint();
  cloudTick();
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
  setCommon(PM,vp,2);gl.uniform4f(PM.u.uTint,sc[0],sc[1],sc[2],0.45);gl.uniform1i(PM.u.uLit,0);gl.uniform3fv(PM.u.uFwd,camAxes().f);
  for(const R of MODELS){if(!R.nsel)continue;gl.bindVertexArray(R.vaoSel);
    for(const s of R.surfs){if(!surfOn(R,s))continue;gl.uniform1i(PM.u.uAuto2,s.lod?1:0);bindMat(PM,s.ti,2);
      gl.drawElementsInstanced(gl.TRIANGLES,s.count,gl.UNSIGNED_INT,s.first*4,R.nsel);}}
  gl.uniform1i(PM.u.uAuto2,0);gl.disable(gl.CULL_FACE);
  gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.useProgram(PL);gl.uniformMatrix4fv(PL.u.uVP,false,vp);
  if(selEdgeCount){
    gl.bindVertexArray(B.vSelE);gl.disableVertexAttribArray(7);gl.vertexAttrib4f(7,sc[0],sc[1],sc[2],1);
    if(view.xray){gl.depthFunc(gl.GREATER);gl.uniform1f(PL.u.uAlpha,0.35);gl.drawElements(gl.LINES,selEdgeCount,gl.UNSIGNED_INT,0);}
    gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,1);gl.drawElements(gl.LINES,selEdgeCount,gl.UNSIGNED_INT,0);
  }
  if(hovEdgeCount||hovBoxVerts){
    const hc=hexRGB(TH.accent);gl.depthFunc(gl.LEQUAL);gl.uniform1f(PL.u.uAlpha,0.9);
    if(hovEdgeCount){gl.bindVertexArray(B.vHovE);gl.disableVertexAttribArray(7);gl.vertexAttrib4f(7,hc[0],hc[1],hc[2],1);
      gl.drawElements(gl.LINES,hovEdgeCount,gl.UNSIGNED_INT,0);}
    if(hovBoxVerts){gl.bindVertexArray(B.vHovBox);gl.vertexAttrib4f(7,hc[0],hc[1],hc[2],1);gl.drawArrays(gl.LINES,0,hovBoxVerts);}
  }
  gl.bindVertexArray(null);gl.depthMask(true);gl.disable(gl.BLEND);gl.depthFunc(gl.LEQUAL);
}

// ---- lines: wireframe, setsize boxes, target links, facing arrows ----------------------
function boxLines(L,mn,mx,c){
  const C=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]];
  for(const[a,b]of[[0,1],[1,3],[3,2],[2,0],[4,5],[5,7],[7,6],[6,4],[0,4],[1,5],[2,6],[3,7]]){const p=C(a),q=C(b);L.push(p[0],p[1],p[2],c[0],c[1],c[2],c[3],q[0],q[1],q[2],c[0],c[1],c[2],c[3]);}
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
    const b=X.box,o=b.origin;
    const c=sel?[sc[0],sc[1],sc[2],1]:[X.col[0],X.col[1],X.col[2],0.85];
    boxLines(sel?H:L,[o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]],[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]],c);
    if(sel){const r=6;H.push(o[0]-r,o[1],o[2],1,1,1,1,o[0]+r,o[1],o[2],1,1,1,1, o[0],o[1]-r,o[2],1,1,1,1,o[0],o[1]+r,o[2],1,1,1,1, o[0],o[1],o[2]-r,1,1,1,1,o[0],o[1],o[2]+r,1,1,1,1);}
  }
  LINKS=[];
  if(view.links){
    for(const X of ENTS){const tg=MAP.ents[X.ei].kvl.target;if(!tg||!X.anchor||!entVisible(X.ei))continue;
      const to=ENTS.tn.get(tg)||[];
      for(const ti of to){const Y=ENTS[ti];if(!Y.anchor||!entVisible(ti))continue;
        const hot=selE.has(X.ei)||selE.has(ti);const c=hot?[sc[0],sc[1],sc[2],1]:[X.col[0],X.col[1],X.col[2],0.75];
        (hot?H:L).push(X.anchor[0],X.anchor[1],X.anchor[2],c[0],c[1],c[2],c[3],Y.anchor[0],Y.anchor[1],Y.anchor[2],c[0],c[1],c[2],c[3]);
        LINKS.push([X.anchor,Y.anchor,c,hot]);}}}
  // facing arrows as MOHRadiant draws them (Brush_DrawFacingAngle): white, from the middle
  // of the box out to 2.5 times its half-width, the head half a half-width long and
  // opening up and down. Drawn as 4-pixel bands each frame (drawFacingArrows).
  ARROWS=[];
  if(view.arrows){
    for(const X of ENTS){if(!X.marker||!X.origin||!entShown(X.ei))continue;
      const e=MAP.ents[X.ei];if(e.kvl.angle==null&&e.kvl.angles==null)continue;
      const ax=anglesAxis(entAngles(e.kvl)), f=ax[0], u=ax[2], o=X.origin, b=X.box||{mins:[-8,-8,-8],maxs:[8,8,8]};
      const c=[o[0]+(b.mins[0]+b.maxs[0])/2,o[1]+(b.mins[1]+b.maxs[1])/2,o[2]+(b.mins[2]+b.maxs[2])/2];
      const hw=Math.max(4,(b.maxs[0]-b.mins[0])/2), len=hw*2.5, t=hw*0.5;
      const tip=[c[0]+f[0]*len,c[1]+f[1]*len,c[2]+f[2]*len];
      const h1=[tip[0]-f[0]*t-u[0]*t,tip[1]-f[1]*t-u[1]*t,tip[2]-f[2]*t-u[2]*t], h2=[h1[0]+u[0]*2*t,h1[1]+u[1]*2*t,h1[2]+u[2]*2*t];
      ARROWS.push([c,tip,h1,h2,selE.has(X.ei)]);
    }
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
function draw2D(){
  ctx.clearRect(0,0,W,H);
  const selE=selectedEnts();
  if(view.labels){
    // Nearest first, never overlapping: named entities out to 2048 units, unnamed ones
    // close by only, lights and static props only when named (there are hundreds).
    const cand=[];
    for(const X of ENTS){if(X.ei===0||!X.anchor||!entVisible(X.ei))continue;
      const sel=selE.has(X.ei), e=MAP.ents[X.ei], tn=e.kvl.targetname;
      if(!sel&&!tn&&(X.hasGeo||X.marker===2||(X.cat&C_STATIC)))continue;
      const d=Math.hypot(X.anchor[0]-cam.pos[0],X.anchor[1]-cam.pos[1],X.anchor[2]-cam.pos[2]);
      if(!sel&&d>(tn?2048:700))continue;
      cand.push([sel?-1:d,X]);}
    cand.sort((a,b)=>a[0]-b[0]);
    ctx.font='11px ui-monospace,Menlo,Consolas,monospace';ctx.textBaseline='middle';
    const taken=[];let shown=0;
    for(const[d,X]of cand){if(shown>=120&&d>=0)break;
      const top=X.box?[X.anchor[0],X.anchor[1],X.anchor[2]+(X.marker&&X.box?X.box.maxs[2]+6:0)]:X.anchor;
      const sp=project(top);if(!sp||sp[0]<-50||sp[0]>W+50||sp[1]<-20||sp[1]>H+20)continue;
      const e=MAP.ents[X.ei], tn=e.kvl.targetname, txt=(e.kvl.classname||'?')+(tn?'  $'+tn:'');
      const tw=ctx.measureText(txt).width, r=[sp[0]-tw/2-4,sp[1]-16,tw+8,14];
      if(d>=0&&taken.some(q=>r[0]<q[0]+q[2]&&q[0]<r[0]+r[2]&&r[1]<q[1]+q[3]&&q[1]<r[1]+r[3]))continue;
      taken.push(r);
      ctx.globalAlpha=d<0?1:Math.max(0.4,1-d/2400);ctx.fillStyle='rgba('+TH.labelbg+',.8)';ctx.fillRect(r[0],r[1],r[2],r[3]);
      ctx.fillStyle=d<0?TH.sel:(tn?TH.accent:TH.txt);ctx.fillText(txt,sp[0]-tw/2,sp[1]-9);
      shown++;}
    ctx.globalAlpha=1;
  }
  if(radFly){ctx.strokeStyle=TH.accent;ctx.globalAlpha=0.8;ctx.lineWidth=1;ctx.beginPath();
    ctx.moveTo(W/2-10,H/2);ctx.lineTo(W/2+10,H/2);ctx.moveTo(W/2,H/2-10);ctx.lineTo(W/2,H/2+10);ctx.stroke();
    ctx.beginPath();ctx.moveTo(W/2,H/2);ctx.lineTo(radFly.x,radFly.y);ctx.stroke();ctx.globalAlpha=1;}
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
      const b=X.box,o=b.origin,g=X.marker?2:0.5;
      const mn=[o[0]+b.mins[0]-g,o[1]+b.mins[1]-g,o[2]+b.mins[2]-g],mx=[o[0]+b.maxs[0]+g,o[1]+b.maxs[1]+g,o[2]+b.maxs[2]+g];
      const C=k=>[(k&1)?mx[0]:mn[0],(k&2)?mx[1]:mn[1],(k&4)?mx[2]:mn[2]];
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
function selectionChanged(){rebuildSelection();refreshHover();updateSelPanel();if($('info').classList.contains('on'))showInfo(infoMode==='errs'?'sel':infoMode);requestDraw();}
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
function selectByTexture(ti,add){
  if(!add)SEL.clear();let n=0;
  for(const f of matFaces[ti]||[]){if(faceVis&&!faceVis[f])continue;const ei=SC.faceEnt[f];
    const k=(ei>0&&!isWorldlike(ei))?'e'+ei:'p'+SC.facePrim[f];if(!SEL.has(k)){SEL.add(k);n++;}}
  flash(n+' brush'+(n===1?'':'es')+' / entities with '+(TEX[ti]?TEX[ti].n.replace(/^textures\//,''):'?')+' selected');
}
function selectClass(cls,add){if(!add)SEL.clear();for(let ei=1;ei<MAP.ents.length;ei++)if(MAP.ents[ei].cls===cls)SEL.add('e'+ei);selectionChanged();}
function selBounds(){
  const mn=[Infinity,Infinity,Infinity],mx=[-Infinity,-Infinity,-Infinity];
  const grow=(a,b)=>{for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],a[k]);mx[k]=Math.max(mx[k],b[k]);}};
  for(const pi of selectedPrims()){const p=SC.prims[pi];if(isFinite(p.mins[0]))grow(p.mins,p.maxs);}
  for(const ei of selectedEnts()){const X=ENTS[ei],b=X.box;
    if(b){const o=b.origin;grow([o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]],[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]]);}
    else if(X.anchor)grow(X.anchor,X.anchor);}
  return isFinite(mn[0])?{mins:mn,maxs:mx}:null;
}
function hideSelection(){
  if(!SEL.size)return;
  for(const k of SEL){if(k[0]==='e')hidEnt.add(+k.slice(1));else hidPrim.add(+k.slice(1));}
  const n=SEL.size;SEL.clear();rebuildWorld();updateSelPanel();flash(n+' hidden - Shift+H shows them again');
}
function unhideAll(){hidEnt.clear();hidPrim.clear();rebuildWorld();updateSelPanel();}

// ============================================================================
//  Camera movement
// ============================================================================
const keys=new Set();
let radFly=null;          // Radiant right-button flight: {x,y} cursor
let flyAnim=null;
function moveBy(v,s){cam.pos[0]+=v[0]*s;cam.pos[1]+=v[1]*s;cam.pos[2]+=v[2]*s;}
let _lastT=performance.now(), _saveT=0;
function loop(t){
  requestAnimationFrame(loop);
  const dt=Math.min(0.1,(t-_lastT)/1000);_lastT=t;
  if(!SC)return;
  let moved=false;
  if(flyAnim){const k=Math.min(1,(t-flyAnim.t0)/flyAnim.dur),s=k*k*(3-2*k);
    for(let i=0;i<3;i++)cam.pos[i]=flyAnim.from[i]+(flyAnim.to[i]-flyAnim.from[i])*s;
    if(flyAnim.yaw!=null){cam.yaw=flyAnim.y0+(flyAnim.yaw-flyAnim.y0)*s;cam.pitch=flyAnim.p0+(flyAnim.pitch-flyAnim.p0)*s;}
    if(k>=1)flyAnim=null;moved=true;}
  const k=c=>keys.has(c), fast=k('Shift')?4:1, a=camAxes(), sp=moveSpeed*fast*dt;
  if(keys.size&&!typing()){
    if(camMode==='free'){
      const F=(k('w')||k('arrowup'))?1:(k('s')||k('arrowdown'))?-1:0, R=k('d')?1:k('a')?-1:0, U=(k(' ')?1:0)-(k('c')?1:0);
      // A / D strafe along the screen's right (the tilted one, a.r) and Space / C rise along
      // the screen's up: world up turned about the view line by the tilt, so with no tilt
      // they go straight up and down, as in the Model Viewer's free-look.
      if(F){moveBy(a.f,sp*F);moved=true;} if(R){moveBy(a.r,sp*R);moved=true;}
      if(U){const P=cam.pitch*Math.PI/180,c=Math.cos(P),s=Math.sin(P);
        moveBy([c*a.u[0]-s*a.f[0],c*a.u[1]-s*a.f[1],c*a.u[2]-s*a.f[2]],sp*U);moved=true;}
      if(k('arrowleft')){lookBy(-90*dt*fast,0);moved=true;} if(k('arrowright')){lookBy(90*dt*fast,0);moved=true;}
      if(k('q')){cam.roll-=60*dt;moved=true;} if(k('e')){cam.roll+=60*dt;moved=true;}
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
  if(moved){camChanged();draw();}
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
  const now=performance.now();
  if(now-_saveT>800){_saveT=now;LS.set('mohaaMapCam:'+D.path,JSON.stringify({p:cam.pos,y:cam.yaw,pi:cam.pitch}));}
  hoverDirty=true;
}
function lookFrom(target,dist){
  const a=camAxes();
  return[target[0]-a.f[0]*dist,target[1]-a.f[1]*dist,target[2]-a.f[2]*dist];
}
function flyTo(pos,yaw,pitch){flyAnim={t0:performance.now(),dur:450,from:cam.pos.slice(),to:pos,y0:cam.yaw,p0:cam.pitch,yaw:yaw,pitch:pitch};
  if(yaw!=null){let d=yaw-cam.yaw;while(d>180)d-=360;while(d<-180)d+=360;flyAnim.yaw=cam.yaw+d;}}
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
  if(drag){
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
    // a wheel pressed down often nudges the mouse, so a middle click gets more slack
    if(Math.abs(e.clientX-drag.sx)+Math.abs(e.clientY-drag.sy)>(drag.b===1?10:4))drag.moved=true;
    if(radFly&&drag.b===2){radFly={x:x,y:y};return;}
    if(!drag.moved)return;
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
  const h=hitInfo(pickAt(x,y),x,y);
  if(d.b===0)clickSelect(h,d.m);
  else if(d.b===1)faceInfoAt(h);
});
glcv.addEventListener('dblclick',e=>{if(SEL.size)focusSelection();});
glcv.addEventListener('wheel',e=>{e.preventDefault();const a=camAxes();
  moveBy(a.f,-Math.sign(e.deltaY)*(e.shiftKey?256:64));camChanged();requestDraw();},{passive:false});
glcv.addEventListener('mouseleave',()=>{hoverAt=null;setHover(null);updateHoverText(null);});
// hover read-out, a few times a second at most
setInterval(()=>{if(!hoverDirty||!hoverAt||drag||!SC||keys.size||flyAnim||radFly)return;hoverDirty=false;
  const h=hitInfo(pickAt(hoverAt[0],hoverAt[1]),hoverAt[0],hoverAt[1]);setHover(h);updateHoverText(h);draw();},90);
function updateHoverText(h){
  const el=$('hintHover');if(_flashT&&el.style.color)return;
  if(!h){el.textContent='';return;}
  let s='';
  if(h.face>=0&&(h.ent===0||isWorldlike(h.ent))){const p=SC.prims[h.prim];s=(p.kind===1?'patch ':p.kind===2?'terrain ':'brush ')+p.bn+(h.ent?' ('+MAP.ents[h.ent].cls+')':'')+' · '+(TEX[SC.faceTex[h.face]]||{n:'?'}).n.replace(/^textures\//,'');}
  else s='entity '+h.ent+' · '+entName(h.ent)+(h.face>=0?' · '+(TEX[SC.faceTex[h.face]]||{n:'?'}).n.replace(/^textures\//,''):'');
  if(h.point)s+=' · '+fvec(h.point);
  el.textContent=s;
}
function updateHint(){
  $('hintCam').textContent=(camMode==='free'?'free-look ':'radiant-look ')+fvec(cam.pos)+'  yaw '+fnum(cam.yaw)+' pitch '+fnum(cam.pitch)+(clipOn?'  clip '+clipDist:'');
}

// ============================================================================
//  Keyboard
// ============================================================================
function typing(){const a=document.activeElement;return a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.tagName==='SELECT');}
const CAM_KEYS_FREE=new Set(['w','a','s','d','q','e','c',' ','arrowup','arrowdown','arrowleft','arrowright']);
const CAM_KEYS_RAD=new Set(['arrowup','arrowdown','arrowleft','arrowright',',','.','d','c','a','z']);
const FILTER_KEYS={'alt+1':C_WORLD,'alt+2':C_ENTITIES,'alt+3':C_PATCH,'alt+4':C_TRANS,'alt+5':C_LIQUID,'alt+6':C_CAULK,
  'alt+7':C_CLIP,'alt+8':C_PATH,'alt+9':C_AINODE,'alt+0':C_LIGHT,'ctrl+d':C_DETAIL,'ctrl+h':C_HINT,'ctrl+m':C_MODEL,
  'ctrl+r':C_TERRAIN,'ctrl+t':C_TRIGGER,'ctrl+p':C_PORTAL,'ctrl+k':C_SKY};
window.addEventListener('keydown',e=>{
  if(typing()){if(e.key==='Escape'){document.activeElement.blur();e.preventDefault();}return;}
  const kl=e.key.length===1?e.key.toLowerCase():e.key.toLowerCase();
  const combo=(e.ctrlKey||e.metaKey?'ctrl+':'')+(e.altKey?'alt+':'')+(/^digit\d$/i.test(e.code)?e.code.slice(5):kl);
  if(FILTER_KEYS[combo]!=null){toggleFilter(FILTER_KEYS[combo]);e.preventDefault();return;}
  if((e.ctrlKey||e.metaKey)&&kl==='f'){$('findIn').focus();$('findIn').select();e.preventDefault();return;}
  if((e.ctrlKey||e.metaKey)&&(kl==='\\'||e.code==='Backslash')){toggleClip();e.preventDefault();return;}
  // camera keys (held)
  const camSet=camMode==='free'?CAM_KEYS_FREE:CAM_KEYS_RAD;
  if(e.key==='Shift'||e.key==='Control'){keys.add(e.key);return;}
  if(camSet.has(kl)&&!e.altKey&&!(e.ctrlKey&&camMode==='free')){
    if(camMode==='rad'&&e.ctrlKey){if(['arrowup','arrowdown',',','.'].includes(kl)){gridStep(kl);e.preventDefault();}return;}
    keys.add(kl);e.preventDefault();return;}
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  switch(kl){
    case 'h':case '?':if(e.shiftKey&&kl==='h'){unhideAll();flash('Everything is shown again');}else toggleHelp();break;
    case 'n':showInfo('sel');break;
    case 'b':toggleFullBright();break;
    case 'k':toggleSimpleSky();break;
    case 'm':toggleSimpleModels();break;
    case 'f':focusSelection();break;
    case 'v':setCamMode(camMode==='free'?'rad':'free');break;
    case 'r':resetCam();break;
    case 'l':toggleLegend();break;
    case 't':themeBtn.click();break;
    case 'end':cam.pitch=0;cam.roll=0;camChanged();requestDraw();break;
    case 'pageup':changeFloor(true);e.preventDefault();break;
    case 'pagedown':changeFloor(false);e.preventDefault();break;
    case '[':setClipDist(clipDist-256);if(!clipOn)toggleClip();break;
    case ']':setClipDist(clipDist+256);if(!clipOn)toggleClip();break;
    case 'backspace':hideSelection();e.preventDefault();break;
    case '/':$('findIn').focus();e.preventDefault();break;
    case '\\':case '|':$('sideTab').click();e.preventDefault();break;
    case 'escape':escape();break;
    default:{const d=DISPLAY.find(x=>x.key===e.key);if(d){toggleDisplay(d.k);}}
  }
});
window.addEventListener('keyup',e=>{const kl=e.key.length===1?e.key.toLowerCase():e.key;keys.delete(kl);keys.delete(kl.toLowerCase());
  if(e.key==='Shift'||e.key==='Control')keys.delete(e.key);});
window.addEventListener('blur',()=>{keys.clear();radFly=null;});
// Ctrl + arrows / comma / period in Radiant-look: one grid step (MOHRadiant's CameraGrid* commands).
function gridStep(kl){const a=camAxes(),g=64;const flat=vnorm([a.f[0],a.f[1],0])||[1,0,0];
  if(kl==='arrowup')moveBy(flat,g);else if(kl==='arrowdown')moveBy(flat,-g);
  else if(kl===',')moveBy(a.r,-g);else if(kl==='.')moveBy(a.r,g);
  camChanged();requestDraw();}
// Esc peels one layer at a time: help or legend, info card, selection, then the map itself.
function escape(){
  if(helpOv.style.display!=='none'){toggleHelp(false);return;}
  if(legOv.style.display!=='none'){toggleLegend(false);return;}
  if($('info').classList.contains('on')){hideInfo();return;}
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
 {k:'xray',l:'X-ray',key:'9',t:'Show the selection\'s outline, box, target links and facing arrow faintly through walls (everything else stays hidden behind them)'}];
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
 {m:C_ORIGIN,l:'Origin',key:'',t:'common/origin brushes (the pivot of doors and movers)'},
 {m:C_NODRAW,l:'Nodraw',key:'',t:'Other editor-only surfaces: nodraw, ladders, rain, and the flat tree pictures that only cast a tree\'s shadow (misc_outside/commontreeshadow)'},
 {m:C_POINT,l:'Point ents',key:'',t:'Other point entities: player starts, script origins, info_* ...'}];
function buildPanel(){
  const db=$('dispBtns');
  for(const d of DISPLAY){const b=document.createElement('button');b.id='d_'+d.k;b.innerHTML=esc(d.l)+'<span class="k">'+d.key+'</span>';
    b.title=d.t+' ('+d.key+')';b.onclick=()=>toggleDisplay(d.k);db.appendChild(b);}
  const fb=$('filtBtns');
  for(const f of FILTERS){const b=document.createElement('button');b.innerHTML=esc(f.l)+(f.key?'<span class="k">'+f.key+'</span>':'');
    b.title=f.t+(f.key?' ('+f.key+')':'')+' - click to show / hide';f.el=b;b.onclick=()=>toggleFilter(f.m);fb.appendChild(b);}
  $('bFull').onclick=toggleFullBright;
  if(!LIT){$('bFull').disabled=true;
    $('bFull').title=D.kind==='bsp'?'This .bsp has no lightmaps, so the game draws it at full brightness too.'
      :'A .map has no lighting yet: the game\'s light is baked when the map is compiled. Open the compiled .bsp to see it.';}
  $('bSimpleSky').onclick=toggleSimpleSky;
  $('bSimpleMod').onclick=toggleSimpleModels;
  $('bShowAll').onclick=()=>{hiddenMask=0;filtersChanged();};
  // the two looks also set the light and the sky: MOHRadiant is always full bright
  $('bGameView').onclick=()=>{hiddenMask=C_CAULK|C_CLIP|C_TRIGGER|C_HINT|C_ORIGIN|C_PORTAL|C_NODRAW|C_POINT|C_LIGHT|C_AINODE|C_PATH|C_VIS;
    simpleSky=false;fullBright=false;filtersChanged();requestDraw();};
  $('bEditView').onclick=()=>{hiddenMask=C_HINT|C_PORTAL;simpleSky=true;fullBright=true;filtersChanged();requestDraw();};
  syncButtons();
  $('bFree').onclick=()=>setCamMode('free');$('bRad').onclick=()=>setCamMode('rad');
  const sp=$('speed');sp.value=moveSpeed;$('speedV').textContent=moveSpeed;sp.oninput=()=>{moveSpeed=+sp.value;$('speedV').textContent=moveSpeed;saveOpts();};
  const fv=$('fov');fv.value=fovX;$('fovV').textContent=fovX;fv.oninput=()=>{fovX=+fv.value;$('fovV').textContent=fovX;saveOpts();requestDraw();};
  const cd=$('clipD');cd.value=clipDist;$('clipV').textContent=clipDist;cd.oninput=()=>setClipDist(+cd.value);
  $('bClip').onclick=toggleClip;$('bClip').classList.toggle('on',clipOn);
  $('gotoIn').addEventListener('keydown',e=>{if(e.key!=='Enter')return;const v=($('gotoIn').value.match(/-?\d+(\.\d+)?/g)||[]).map(Number);
    if(v.length>=3){flyTo([v[0],v[1],v[2]],null,null);$('gotoIn').blur();}else flash('Type three numbers: x y z');});
  $('bCopyCam').onclick=()=>copyText(fvec(cam.pos));
  $('bInfo').onclick=()=>showInfo('sel');$('bFocus').onclick=focusSelection;$('bHide').onclick=hideSelection;
  $('bClear').onclick=()=>{SEL.clear();selectionChanged();};$('bUnhide').onclick=unhideAll;
  $('bSame').onclick=()=>{if(lastHit)selectSameKind(lastHit,false);};
  $('bPath').onclick=()=>{const ei=+$('bPath').dataset.ei;if(ei>0)selectPath({ent:ei,face:-1,prim:-1,point:null},false);};
  $('infoClose').onclick=hideInfo;$('infoCopy').onclick=()=>copyText($('infoBody').innerText);
  $('tabFind').onclick=()=>setTab('find');$('tabCls').onclick=()=>setTab('cls');$('tabTex').onclick=()=>setTab('tex');
  const fi=$('findIn');let ft=null;
  fi.addEventListener('input',()=>{clearTimeout(ft);ft=setTimeout(()=>{setTab('find');},150);});
  fi.addEventListener('keydown',e=>{if(e.key==='Enter'){setTab('find');selectFindResults();e.preventDefault();}});
}
function syncButtons(){
  for(const d of DISPLAY){const b=$('d_'+d.k);if(b)b.classList.toggle('on',!!view[d.k]);}
  for(const f of FILTERS)f.el.classList.toggle('on',!(hiddenMask&f.m));
  $('bFull').classList.toggle('on',fullBright||!LIT);
  $('bSimpleSky').classList.toggle('on',simpleSky);
  $('bSimpleMod').classList.toggle('on',simpleModels);
  $('bFree').classList.toggle('on',camMode==='free');$('bRad').classList.toggle('on',camMode==='rad');
  $('camHelpFree').style.display=camMode==='free'?'':'none';$('camHelpRad').style.display=camMode==='rad'?'':'none';
}
function toggleDisplay(k){view[k]=!view[k];syncButtons();saveOpts();
  if(k==='wire'&&view.wire)rebuildWire();
  if(k==='fog'&&view.fog&&!FOG.far)flash('This map has no farplane fog');
  lineDirty=true;requestDraw();}
function toggleFilter(m){if((hiddenMask&m)===m)hiddenMask&=~m;else hiddenMask|=m;filtersChanged();}
function toggleSimpleSky(){
  simpleSky=!simpleSky;syncButtons();saveOpts();requestDraw();
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
function filtersChanged(){syncButtons();saveOpts();rebuildWorld();updateSelPanel();}
function setCamMode(m){camMode=m;keys.clear();radFly=null;syncButtons();saveOpts();requestDraw();}
function setClipDist(v){clipDist=Math.max(128,Math.min(32768,v));$('clipD').value=clipDist;$('clipV').textContent=clipDist;saveOpts();requestDraw();}
function toggleClip(){clipOn=!clipOn;$('bClip').classList.toggle('on',clipOn);saveOpts();requestDraw();}
function saveOpts(){LS.set('mohaaMapViewerOpts',JSON.stringify({view:view,hidden:hiddenMask,mode:camMode,speed:moveSpeed,fov:fovX,clip:clipOn,clipD:clipDist,fb:fullBright,ss:simpleSky,sm:simpleModels}));}
function loadOpts(){try{const o=JSON.parse(LS.get('mohaaMapViewerOpts')||'null');if(!o)return;
  for(const k in view)if(k in (o.view||{}))view[k]=!!o.view[k];
  fullBright=!!o.fb;simpleSky=!!o.ss;simpleModels=!!o.sm;
  if(typeof o.hidden==='number')hiddenMask=o.hidden;if(o.mode==='rad'||o.mode==='free')camMode=o.mode;
  // static models have no Show button of their own any more (Models and Entities hide them)
  if((hiddenMask&C_ENTITIES)!==C_ENTITIES)hiddenMask&=~C_STATIC;
  if(o.speed>0)moveSpeed=o.speed;if(o.fov>0)fovX=Math.max(60,Math.min(150,o.fov));clipOn=!!o.clip;if(o.clipD>0)clipDist=o.clipD;}catch(_e){}}

function updateSelPanel(){
  const n=SEL.size;$('selBtns').style.display=n?'':'none';
  const hid=hidEnt.size+hidPrim.size;$('hidLine').style.display=hid?'':'none';$('hidCount').textContent=hid+' hidden';
  const el=$('selSum');
  if(!n){el.textContent='Click anything in the map to select it.';el.className='co';return;}
  el.className='';
  const ents=[...selectedEnts()], prims=selectedPrims();
  // Same path: the path through the one selected entity (else the last one clicked), when
  // its "target" leads somewhere or something targets it (as Ctrl+Alt+click)
  const pe=ents.length===1?ents[0]:(lastHit&&lastHit.ent>0&&SEL.has('e'+lastHit.ent))?lastHit.ent:-1;
  const pp=(pe>0&&!isWorldlike(pe))?pathOf(pe):null;
  $('bPath').style.display=(pp&&(pp.before.size||pp.after.size))?'':'none';$('bPath').dataset.ei=pe;
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
function setTab(t){curTab=t;for(const[id,k]of[['tabFind','find'],['tabCls','cls'],['tabTex','tex']])$(id).classList.toggle('on',k===t);renderList();}
let SEARCH=null;
function searchText(ei){if(!SEARCH)SEARCH=MAP.ents.map(e=>e.kv.map(kv=>kv[0]+' '+kv[1]).join(' \u0001 ').toLowerCase());return SEARCH[ei];}
function runFind(q){
  q=q.trim().toLowerCase();findRes=[];if(!q)return;
  const words=q.split(/\s+/);
  for(let ei=0;ei<MAP.ents.length;ei++){const t=searchText(ei);if(words.every(w=>t.includes(w)))findRes.push({e:ei});}
  const used=texCounts();
  for(const[ti,c]of used){const nm=TEX[ti].n.replace(/^textures\//,'');if(words.every(w=>nm.includes(w)))findRes.push({t:ti,c:c});}
}
let _texCounts=null;
function texCounts(){if(_texCounts)return _texCounts;const m=new Map();for(let f=0;f<SC.nf;f++){const t=SC.faceTex[f];m.set(t,(m.get(t)||0)+1);}
  for(const R of MODELS)for(const s of R.surfs)m.set(s.ti,(m.get(s.ti)||0)+R.inst.length);
  _texCounts=[...m.entries()].sort((a,b)=>TEX[a[0]].n<TEX[b[0]].n?-1:1);return _texCounts;}
const openCls=new Set();
function renderList(){
  const box=$('listBox');const rows=[];
  const entRow=(ei,sub)=>{const e=MAP.ents[ei],X=ENTS[ei],sel=SEL.has('e'+ei)||(ei===0);
    const where=X.anchor?fvec(X.anchor):'';
    return '<div class="li'+(sub?' sub':'')+(sel?' sel':'')+'" data-e="'+ei+'"><span class="sw" style="background:rgb('+X.col.map(v=>Math.round(v*255)).join(',')+')"></span><span class="nm">'+
      esc(sub?(e.kvl.targetname?'$'+e.kvl.targetname:'entity '+ei):(e.kvl.classname||'?')+(e.kvl.targetname?'  $'+e.kvl.targetname:''))+'</span><span class="ct">'+esc(where)+'</span></div>';};
  if(curTab==='find'){
    runFind($('findIn').value);
    if(!$('findIn').value.trim())rows.push('<div class="co">Type above to search every key and value (classname, targetname, target, model, spawnflags...) and every texture name. Enter selects everything found.</div>');
    else if(!findRes.length)rows.push('<div class="co">Nothing matches.</div>');
    let n=0;for(const r of findRes){if(++n>600){rows.push('<div class="co">... '+(findRes.length-600)+' more (Enter selects them all)</div>');break;}
      if(r.e!=null)rows.push(entRow(r.e,false));
      else rows.push(texRow(r.t,r.c));}
  }else if(curTab==='cls'){
    const cnt=new Map();for(let ei=0;ei<MAP.ents.length;ei++){const c=MAP.ents[ei].kvl.classname||'?';if(!cnt.has(c))cnt.set(c,[]);cnt.get(c).push(ei);}
    const names=[...cnt.keys()].sort((a,b)=>a.toLowerCase()<b.toLowerCase()?-1:1);
    rows.push('<div class="co" style="margin-bottom:4px">'+MAP.ents.length+' entities · '+names.length+' classes · click a class to select them all, the arrow to list them</div>');
    for(const c of names){const l=cnt.get(c),open=openCls.has(c),X=ENTS[l[0]];
      rows.push('<div class="li" data-c="'+esc(c)+'"><span class="ar" data-o="'+esc(c)+'">'+(open?'▾':'▸')+'</span><span class="sw" style="background:rgb('+(X.ccol||X.col).map(v=>Math.round(v*255)).join(',')+')"></span><span class="nm">'+esc(c)+'</span><span class="ct">'+l.length+'</span></div>');
      if(open)for(const ei of l.slice(0,500))rows.push(entRow(ei,true));}
  }else{
    const used=texCounts();
    rows.push('<div class="co" style="margin-bottom:4px">'+used.length+' textures · click one to select every brush using it</div>');
    for(const[ti,c]of used)rows.push(texRow(ti,c));
  }
  box.innerHTML=rows.join('');
}
function texRow(ti,c){const te=TEX[ti],u=TEXURL[ti];
  return '<div class="li" data-t="'+ti+'">'+(u?'<img src="'+u+'" alt="">':'<span class="sw" style="width:18px;height:18px;background:rgb('+(te.c||[.5,.5,.5]).map(v=>Math.round(v*255)).join(',')+')"></span>')+
    '<span class="nm">'+esc(te.n.replace(/^textures\//,''))+(te.f&TF_MISSING?' <span style="color:var(--err)">(missing)</span>':'')+'</span><span class="ct">'+c+'</span></div>';}
$('listBox').addEventListener('click',e=>{
  const o=e.target.closest('[data-o]');if(o){const c=o.getAttribute('data-o');if(openCls.has(c))openCls.delete(c);else openCls.add(c);renderList();return;}
  const r=e.target.closest('.li');if(!r)return;
  if(r.hasAttribute('data-e')){const ei=+r.getAttribute('data-e');SEL.clear();if(ei)SEL.add('e'+ei);selectionChanged();if(ei)focusSelection();renderList();}
  else if(r.hasAttribute('data-c')){selectClass(r.getAttribute('data-c'),e.shiftKey);renderList();}
  else if(r.hasAttribute('data-t')){selectByTexture(+r.getAttribute('data-t'),e.shiftKey);selectionChanged();renderList();}
});
$('listBox').addEventListener('dblclick',e=>{const r=e.target.closest('.li');if(r&&(r.hasAttribute('data-c')||r.hasAttribute('data-t')))focusSelection();});
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
function spawnflagNames(ei){
  const e=MAP.ents[ei], v=parseInt(e.kvl.spawnflags||'0',10)>>>0;if(!v)return '';
  const d=(D.defs||{})[e.cls], names=d&&d.f?d.f:[], ed=D.editorFlags||{}, out=[];
  for(let b=0;b<32;b++)if(v&(1<<b)>>>0){let nm=(b<names.length&&names[b].toLowerCase()!=='x')?names[b]:(ed[b]||'');out.push(((1<<b)>>>0)+(nm?' '+nm:''));}
  return out.join(', ');
}
function srcText(a,b){return D.srcText.slice(a,b);}
function card(title,body){$('infoTitle').textContent=title;$('infoBody').innerHTML=body;$('info').classList.add('on');$('infoBody').scrollTop=0;}
function kvTable(rows){return '<table>'+rows.map(r=>'<tr><td class="k">'+esc(r[0])+'</td><td>'+r[1]+'</td></tr>').join('')+'</table>';}
function copyBtn(text,label){return ' <button class="sm" data-copy="'+esc(text)+'">'+(label||'Copy')+'</button>';}
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
$('stats').addEventListener('click',e=>{if(e.target.closest('[data-errs]'))showInfo('errs');});
function showInfo(mode){
  infoMode=mode||'sel';
  if(infoMode==='errs')return infoErrors();
  if(infoMode==='face'){if(lastHit&&lastHit.face>=0)return infoFace(lastHit);}
  if(!SEL.size){if(lastHit&&lastHit.face>=0&&infoMode!=='sel')return infoFace(lastHit);card('Nothing selected','<div class="note">Click a brush or entity first (Ctrl+click opens this card straight away).</div>');return;}
  const ents=[...selectedEnts()], prims=selectedPrims();
  if(SEL.size===1&&ents.length===1)return infoEntity(ents[0]);
  if(SEL.size===1&&prims.length===1)return infoPrim(prims[0]);
  return infoMulti(ents,prims);
}
function linkEnt(ei){return '<a data-sel="'+ei+'">'+esc(entName(ei))+'</a> <span class="co">(entity '+ei+')</span>';}
function infoEntity(ei){
  const e=MAP.ents[ei],X=ENTS[ei],cls=e.kvl.classname||'?',tn=e.kvl.targetname,b=X.box,def=X.def;
  let h='';
  h+='<div><span class="sw" style="background:rgb('+X.col.map(v=>Math.round(v*255)).join(',')+')"></span><b>'+esc(cls)+'</b>'+(tn?'  <span style="color:var(--accent)">$'+esc(tn)+'</span>':'')+'</div>';
  h+='<div class="note">entity '+ei+' in the .map'+(e.prims.length?' · '+e.prims.filter(p=>p&&p.kind===0).length+' brush(es)'+(e.patches.length?', '+e.patches.length+' patch(es)':'')+(e.terrains.length?', '+e.terrains.length+' terrain block(s)':''):'')+
     (X.model>=0?' · model '+esc(D.models[X.model].p):'')+'</div>';
  if(b){
    const o=b.origin, amin=[o[0]+b.mins[0],o[1]+b.mins[1],o[2]+b.mins[2]], amax=[o[0]+b.maxs[0],o[1]+b.maxs[1],o[2]+b.maxs[2]];
    const ss='setsize '+fvec(b.mins)+' '+fvec(b.maxs);
    h+='<h4>Origin and setsize<span class="sp"></span>'+copyBtn(fvec(o)+'\n'+ss,'Copy')+'</h4>';
    h+=kvTable([['origin',esc(fvec(o))+copyBtn(fvec(o))],['setsize',esc(fvec(b.mins)+' '+fvec(b.maxs))+copyBtn(ss)],
      ['size',esc(fvec([b.maxs[0]-b.mins[0],b.maxs[1]-b.mins[1],b.maxs[2]-b.mins[2]]))],
      ['absmin',esc(fvec(amin))],['absmax',esc(fvec(amax))]]);
    h+='<div class="note'+(b.exact?'':' warn')+'">'+(b.exact?'From: ':'Approximate - from: ')+esc(b.how)+'</div>';
    if(!b.exact&&X.hasGeo)h+='<div class="note">MOHAA keeps no readable setsize for brush entities, so this is the box around its brushes measured from where the compiler puts its origin. Open the .bsp instead of the .map for the exact box.</div>';
    // script lines
    const name=tn?'$'+tn:'local.ent';
    const ang=(e.kvl.angles||e.kvl.angle)?fvec(entAngles(e.kvl)):null;
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
  // textures of a brush entity
  if(X.hasGeo){const cnt=new Map();for(const pi of primsOfEnt(ei)){const p=SC.prims[pi];for(let f=p.f0;f<p.f1;f++){const t=SC.faceTex[f];cnt.set(t,(cnt.get(t)||0)+1);}}
    if(cnt.size){h+='<h4>Textures</h4>'+kvTable([...cnt.entries()].map(([t,c])=>[c+'x','<a data-tex="'+t+'">'+esc(TEX[t].n.replace(/^textures\//,''))+'</a>']));}}
  if(lastHit&&lastHit.ent===ei&&lastHit.face>=0)h+=faceHtml(lastHit.face,true);
  if(def&&def.d)h+='<h4>About '+esc(def.n)+'</h4><div class="desc">'+esc(def.d)+'</div>'+(def.s?'<div class="note">from '+esc(def.s)+'</div>':'');
  h+='<h4>.map source<span class="sp"></span>'+copyBtn(srcText(e.ts,e.te),'Copy')+'</h4><pre>'+esc(clipText(srcText(e.ts,e.te)))+'</pre>';
  card(entName(ei),h);
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
  h+='<h4>.map source<span class="sp"></span>'+copyBtn(srcText(pr.ts,pr.te),'Copy')+'</h4><pre>'+esc(clipText(srcText(pr.ts,pr.te)))+'</pre>';
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
  const s=e.target.closest('[data-sel]');if(s){const ei=+s.getAttribute('data-sel');SEL.clear();SEL.add('e'+ei);lastHit=null;selectionChanged();focusSelection();showInfo('sel');return;}
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
//  Start up
// ============================================================================
async function main(){
  try{
    setLoad('Unpacking map data…',0.05);await tick();
    D=await loadData();
    setLoad('Reading the .map…',0.15);await tick();
    D.srcText=new TextDecoder('windows-1252').decode(D.bytes(D.src));
    MAP=readMap(D.srcText);
    TEX=(D.tex||[]).map((t,i)=>Object.assign({},t,{i:i}));
    for(const t of TEX)TEXI.set(t.n,t);
    setLoad('Building brushes, patches and terrain…',0.3);await tick();
    SC=buildScene(MAP,texFor,null);
    NF=SC.nf;
    buildEntities();
    prepMaterials();
    prepSeeThrough();
    if(D.lit){setLoad('Lighting the game\'s polygons…',0.6);await tick();LIT=buildLit();}
    const wk=MAP.ents[0]?MAP.ents[0].kvl:{};
    FOG.far=parseFloat(wk.farplane)||0;FOG.col=parseVec(wk.farplane_color,3)||[0.5,0.5,0.5];
    setLoad('Uploading to the graphics card…',0.8);await tick();
    loadOpts();
    initGL();
    buildPanel();
    loadTextures();
    resize();
    rebuildWorld();
    // camera: where you left it on this map, else the player start
    let saved=null;try{saved=JSON.parse(LS.get('mohaaMapCam:'+D.path)||'null');}catch(_e){}
    const s=(saved&&saved.p)?{p:saved.p,y:saved.y,pi:saved.pi}:startView();
    cam.pos=s.p.slice();cam.yaw=s.y||0;cam.pitch=s.pi||0;
    $('ttl').textContent=TITLE;
    const nb=MAP.ents.reduce((a,e)=>a+e.brushes.length,0),np=MAP.ents.reduce((a,e)=>a+e.patches.length,0),nt=MAP.ents.reduce((a,e)=>a+e.terrains.length,0);
    $('stats').innerHTML=nb+' brushes · '+np+' patches · '+nt+' terrain<br>'+MAP.ents.length+' entities · '+(D.models||[]).length+' models · '+TEX.length+' textures'+
      (D.kind==='bsp'?'<br>decompiled from the .bsp (v'+(D.bsp&&D.bsp.version)+')':'')+
      (MAP.errors.length?'<br><a class="errlink" data-errs title="Which blocks, where they are in the .map, and why">'+MAP.errors.length+' unreadable block'+(MAP.errors.length===1?'':'s')+' skipped</a>':'');
    $('msgLine').textContent=wk.message?'"'+wk.message+'"':'';
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
main();
</script>
</body></html>
"""
