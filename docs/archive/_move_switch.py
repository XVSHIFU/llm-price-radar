# -*- coding: utf-8 -*-
"""把国际/国内切换器移到 Z.AI 供应商分组标题后面（分组级控制）"""
path = 'index.html'
html = open(path, encoding='utf-8').read()
log = []

# ===== 1. planCur：region 读取改为按 provider 优先 =====
# 原: const planRegionName=x=>hasRegions(x)?(state.planRegion[x.id]||'国际'):null;
old_rn = "const planRegionName=x=>hasRegions(x)?(state.planRegion[x.id]||'国际'):null;"
new_rn = "const planRegionName=x=>hasRegions(x)?(state.planRegion[x.provider]||'国际'):null;"
if old_rn in html:
    html = html.replace(old_rn, new_rn, 1)
    log.append('planRegionName 改按 provider')
else:
    log.append('WARN planRegionName 未匹配')

# ===== 2. regionSwitchHtml：data-plan 改为 data-provider =====
old_rs = "const regionSwitchHtml=x=>{if(!hasRegions(x))return'';const cur=planRegionName(x)||'国际';const opts=Object.keys(x.regions);return '<div class=\"region-switch\" role=\"group\" aria-label=\"选择地区\">'+opts.map(r=>'<button data-region=\"'+E(r)+'\" data-plan=\"'+E(x.id)+'\" class=\"'+(r===cur?'on':'')+'\">'+E(r)+'</button>').join('')+'</div>'};"
new_rs = "const regionSwitchHtml=x=>{if(!hasRegions(x))return'';const cur=planRegionName(x)||'国际';const opts=Object.keys(x.regions);return '<div class=\"region-switch\" role=\"group\" aria-label=\"选择地区\">'+opts.map(r=>'<button data-region=\"'+E(r)+'\" data-provider=\"'+E(x.provider)+'\" class=\"'+(r===cur?'on':'')+'\">'+E(r)+'</button>').join('')+'</div>'};"
if old_rs in html:
    html = html.replace(old_rs, new_rs, 1)
    log.append('regionSwitchHtml 改 data-provider')
else:
    log.append('WARN regionSwitchHtml 未匹配')

# ===== 3. renderRow：移除行内切换器（把 ${hasRegions(x)?...} 那段去掉） =====
old_row = '${hasRegions(x)?`<span class="row-region">${regionSwitchHtml(x)}</span>`:\'\'}'
new_row = ''
if old_row in html:
    html = html.replace(old_row, new_row, 1)
    log.append('renderRow 移除行内切换器')
else:
    log.append('WARN renderRow 切换器段未匹配')

# ===== 4. renderDetail：移除详情内切换器 =====
old_det = '${regionSwitchHtml(x)}<div class="plan-main-price">'
new_det = '<div class="plan-main-price">'
if old_det in html:
    html = html.replace(old_det, new_det, 1)
    log.append('renderDetail 移除详情切换器')
else:
    log.append('WARN renderDetail 切换器段未匹配')

# ===== 5. vendor-label 后加分组切换器（line 97 body 生成） =====
old_body = "const body=[...groupMap.values()].map(items=>`<section class=\"vendor-group\"><h3 class=\"vendor-label\">${state.sort==='default'?mark(items[0].provider)+E(items[0].provider):E(items[0].currency+' 原价')}<small>${items[0].currency} · ${items.length} ${mode()==='models'?'个模型':'个套餐'}</small></h3>${items.map(renderRow).join('')}</section>`).join('');"
new_body = "const body=[...groupMap.values()].map(items=>`<section class=\"vendor-group\"><h3 class=\"vendor-label\">${state.sort==='default'?mark(items[0].provider)+E(items[0].provider):E(items[0].currency+' 原价')}<small>${items[0].currency} · ${items.length} ${mode()==='models'?'个模型':'个套餐'}</small></h3>${mode()==='plans'&&items.some(hasRegions)?groupRegionSwitch(items):''}${items.map(renderRow).join('')}</section>`).join('');"
if old_body in html:
    html = html.replace(old_body, new_body, 1)
    log.append('vendor-label 后加分组切换器')
else:
    log.append('WARN body 生成未匹配')

# ===== 6. 新增 groupRegionSwitch 辅助函数（加在 regionSwitchHtml 后） =====
anchor = "const regionSwitchHtml=x=>{if(!hasRegions(x))return'';"
# 在 regionSwitchHtml 定义后追加 groupRegionSwitch
idx = html.find("const regionSwitchHtml=x=>")
if idx >= 0:
    # 找到 regionSwitchHtml 结尾 '};' 
    end = html.find('};', idx)
    helper = ("const groupRegionSwitch=items=>{"
              "const p=items[0].provider,opts=Object.keys(items.find(hasRegions).regions);"
              "const cur=state.planRegion[p]||'国际';"
              "return '<div class=\"region-switch group-region\" role=\"group\" aria-label=\"选择地区\">'+"
              "opts.map(r=>'<button data-region=\"'+E(r)+'\" data-provider=\"'+E(p)+'\" class=\"'+(r===cur?'on':'')+'\">'+E(r)+'</button>').join('')+'</div>';};")
    html = html[:end+2] + helper + html[end+2:]
    log.append('新增 groupRegionSwitch')
else:
    log.append('WARN 找不到 regionSwitchHtml')

# ===== 7. click 事件：data-provider 更新 state.planRegion =====
old_click = "if(b.dataset.region){state.planRegion[b.dataset.plan]=b.dataset.region;"
new_click = "if(b.dataset.region){state.planRegion[b.dataset.provider]=b.dataset.region;"
if old_click in html:
    html = html.replace(old_click, new_click, 1)
    log.append('click 事件改 data-provider')
else:
    log.append('WARN click 事件未匹配')

open(path, 'w', encoding='utf-8').write(html)
for l in log:
    print('OK:', l)
