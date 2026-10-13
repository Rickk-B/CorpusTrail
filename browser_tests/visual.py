"""Small explicit pixel comparator; importing it needs no browser dependency."""
import hashlib
import json
from pathlib import Path
import platform
import sys

CHANNEL_TOLERANCE = 16
MAX_CHANGED_RATIO = .0005
MAX_TILE_RATIO = .02


def rendering_environment(browser_version):
    directory=Path('/usr/share/fonts/truetype/dejavu')
    names=('DejaVuSans-Bold.ttf','DejaVuSans.ttf','DejaVuSansMono-Bold.ttf','DejaVuSansMono-BoldOblique.ttf',
           'DejaVuSansMono-Oblique.ttf','DejaVuSansMono.ttf','DejaVuSerif-Bold.ttf','DejaVuSerif.ttf')
    fonts={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in names if (directory/name).is_file()}
    if sys.platform=='linux' and len(fonts)!=len(names):
        raise ValueError('Install fonts-dejavu-core for the controlled Linux browser renderer')
    return {'schema': 'corpustrail-browser-renderer/v1', 'browser': 'chromium',
            'browser_version': browser_version, 'platform': sys.platform,
            'machine': platform.machine(), 'device_scale_factor': 1,
            'fonts_sha256': fonts,
            'fontconfig_sha256':hashlib.sha256(Path(__file__).with_name('fonts.conf').read_bytes()).hexdigest(),
            'font': 'DejaVu Sans' if sys.platform=='linux' else 'platform system-ui (not compared)', 'locale': 'en-US', 'timezone': 'UTC',
            'channel_tolerance': CHANNEL_TOLERANCE, 'max_changed_ratio': MAX_CHANGED_RATIO,
            'max_tile_ratio': MAX_TILE_RATIO}


def compare(expected, actual, difference):
    from PIL import Image, ImageChops
    with Image.open(expected) as image: before=image.convert('RGB')
    with Image.open(actual) as image: after=image.convert('RGB')
    if before.size!=after.size:
        return {'passed':False,'reason':'Screenshot dimensions changed','expected':before.size,'actual':after.size}
    delta=ImageChops.difference(before,after)
    channels=delta.split()
    maximum=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    mask=maximum.point(lambda value:255 if value>CHANNEL_TOLERANCE else 0)
    changed=mask.histogram()[255]
    ratio=changed/(mask.width*mask.height)
    tile_ratio=0
    for y in range(0,mask.height,100):
        for x in range(0,mask.width,100):
            tile=mask.crop((x,y,min(x+100,mask.width),min(y+100,mask.height)))
            tile_ratio=max(tile_ratio,tile.histogram()[255]/(tile.width*tile.height))
    passed=ratio<=MAX_CHANGED_RATIO and tile_ratio<=MAX_TILE_RATIO
    if not passed:
        delta.save(difference)
    return {'passed':passed,'changed_pixels':changed,'changed_ratio':ratio,'max_tile_ratio':tile_ratio}


def approve(report, destination, *, reviewed):
    """Explicit review action, separate from running or failing any test."""
    import shutil
    if not reviewed:
        raise ValueError('Baseline approval requires --reviewed after inspecting screenshots')
    value=json.loads((report/'report.json').read_text(encoding='utf-8'))
    if value['mode']!='capture' or not value['passed'] or value['environment']['platform']!='linux':
        raise ValueError('Approve only a passing Linux capture run, never a failed comparison')
    # Do not bless a partial run and silently discard other reviewed images.
    if value['suite']!='all' or value['viewports']!=['desktop','laptop','narrow']:
        raise ValueError('Approval requires a complete three-viewport capture')
    images={}
    for snapshot in value['screenshots']:
        path=report/snapshot['path']
        if path.is_symlink() or not path.is_file() or path.parent!=report/'screenshots' or not path.resolve().is_relative_to(report.resolve()):
            raise ValueError('Invalid candidate screenshot path')
        images[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    destination.mkdir(parents=True,exist_ok=True)
    if destination.is_symlink() or any((destination/name).is_symlink() for name in (*images,'manifest.json')):
        raise ValueError('Baseline approval cannot follow symlinks')
    for name in images:
        shutil.copyfile(report/'screenshots'/name,destination/name)
    (destination/'manifest.json').write_text(json.dumps({'schema':'corpustrail-browser-baselines/v1',
        'environment':value['environment'],'images_sha256':images,
        'review':'Explicitly approved after direct image inspection; not automatic test updates.'},indent=2)+'\n',encoding='utf-8')
