"""One CP7 exception: evidence of repeated existing path-mask rows, not a pass.

Original images, strict results and pixel thresholds are never changed. This
accounts for every raster row: only repeated, identical rows THROUGH an existing
path rectangle may differ in multiplicity, plus consequent viewport-floor blank
space. Non-path pixels retain the existing strict noise budgets, never wider ones.
No cropped, normalized, repainted or additional masked image is produced.
"""
import hashlib
import json
from collections import Counter
from .visual import CHANNEL_TOLERANCE,MAX_CHANGED_RATIO,MAX_TILE_RATIO

POLICY='researcher-approved-cp7-fixture-path-reflow/v1'
CAPTURES={v+'-'+n+'.png' for v in ('desktop','narrow') for n in ('wizard','projects','trash-confirmation')}
CAPTURES.update(v+'-wizard-summary.png' for v in ('desktop','laptop','narrow'))
COLOR=bytes((226,236,238))


def residual_noise(before,after,width):
    """Account for all corresponding pixels without writing altered images."""
    tiles={};changed=0;height=len(before)
    for y,(left,right) in enumerate(zip(before,after)):
        if left==right:continue
        for x in range(width):
            i=x*3
            if max(abs(left[i+c]-right[i+c]) for c in range(3))>CHANNEL_TOLERANCE:
                changed+=1;tile=(x//100,y//100);tiles[tile]=tiles.get(tile,0)+1
    ratio=changed/(width*height)
    tile_ratio=max((count/(min(100,width-x*100)*min(100,height-y*100)) for (x,y),count in tiles.items()),default=0)
    return {'passed':ratio<=MAX_CHANGED_RATIO and tile_ratio<=MAX_TILE_RATIO,
        'changed_pixels':changed,'changed_ratio':ratio,'max_tile_ratio':tile_ratio,
        'channel_tolerance':CHANNEL_TOLERANCE,'max_changed_ratio':MAX_CHANGED_RATIO,'max_tile_ratio_limit':MAX_TILE_RATIO}


def path_reflow_evidence(expected,actual,*,environment,capture,paths,viewport_height):
    from PIL import Image
    rejected={'verified':False,'policy':POLICY}
    if environment.get('platform')!='darwin' or environment.get('browser') not in ('chromium','webkit') or capture not in CAPTURES:
        return rejected
    if not paths or not all(p['truthful'] and p['contained'] and p['overflow']<=1 and p['line_height']==24 for p in paths):
        return rejected
    def rows(path):
        with Image.open(path) as image:
            image=image.convert('RGB');width,height=image.size;body=image.tobytes()
        lines=[body[y*width*3:(y+1)*width*3] for y in range(height)]
        # Only the uniform final canvas background can absorb reflow when the
        # page is constrained by the original viewport's minimum height.
        tail=0
        if height==viewport_height:
            bg=lines[-1]
            if bg!=bg[:3]*width:return None
            while tail<len(lines) and lines[-1-tail]==bg:tail+=1
        end=len(lines)-max(0,tail-1);proof=[];runs=[];index=0
        def span(line):
            left=line.find(COLOR*200)
            if left<0 or left%3:return None
            right=left+600
            while right<len(line) and line[right:right+3]==COLOR:right+=3
            return left//3,(right-left)//3
        while index<end:
            line=lines[index];next_index=index+1
            # A path rectangle is at least 200px wide; small header badges
            # cannot qualify. Every full row, including unmasked gutters, is
            # checked against the repeated row using the UNCHANGED noise rule.
            band=span(line)
            if band:
                while next_index<end and span(lines[next_index])==band:next_index+=1
            else:
                while next_index<end and lines[next_index]==line:next_index+=1
            count=next_index-index
            if band and count>=24:
                content=lines[index:next_index];canonical=Counter(content).most_common(1)[0][0]
                noise=residual_noise([canonical]*count,content,width)
                if not noise['passed']:return None
                runs.append({'y':index,'rows':count,'x':band[0],'width':band[1],
                    'row_sha256':hashlib.sha256(canonical).hexdigest(),'row_noise':noise})
                proof.append(canonical)
            else:proof.extend([line]*count)
            index=next_index
        return width,height,proof,runs,tail
    before=rows(expected);after=rows(actual)
    if before is None or after is None:return rejected
    bw,bh,brows,bruns,btail=before;aw,ah,arows,aruns,atail=after
    if bw!=aw or bw!={'desktop':1440,'laptop':1280,'narrow':390}[capture.split('-')[0]] or bh<viewport_height or ah<viewport_height or len(brows)!=len(arows) or not bruns or len(bruns)!=len(aruns):
        return {**rejected,'reason':'Row accounting or dimensions differ','before_runs':bruns,'after_runs':aruns,'accounted_heights':[len(brows),len(arows)]}
    changes=[b['rows']-a['rows'] for a,b in zip(bruns,aruns)]
    if not any(changes) or any(n%24 for n in changes):return {**rejected,'reason':'Not whole path lines','changes':changes}
    if any(a['row_sha256']!=b['row_sha256'] for a,b in zip(bruns,aruns)):return {**rejected,'reason':'Path row patterns differ'}
    if ah-bh!=sum(changes)+(atail-btail):return {**rejected,'reason':'Unaccounted height change'}
    # Current raster path runs must correspond to the actual DOM path boxes.
    if len(aruns)!=len(paths) or any(abs(run['rows']-p['height'])>1 for run,p in zip(aruns,paths)):return {**rejected,'reason':'DOM path geometry differs from raster'}
    residual=residual_noise(brows,arows,bw)
    if not residual['passed']:return {**rejected,'reason':'Non-path pixels differ','residual':residual}
    result={'verified':True,'policy':POLICY,'capture':capture,
        'expected_sha256':hashlib.sha256(expected.read_bytes()).hexdigest(),
        'actual_sha256':hashlib.sha256(actual.read_bytes()).hexdigest(),
        'expected_size':[bw,bh],'actual_size':[aw,ah],
        'expected_path_runs':bruns,'actual_path_runs':aruns,
        'expected_viewport_floor_rows':btail,'actual_viewport_floor_rows':atail,
        'all_other_pixels_accounted':True,'residual_noise':residual,'path_checks':paths,
        'strict_comparison_passed':False,'researcher_cp7_acceptance':False}
    result['evidence_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result
