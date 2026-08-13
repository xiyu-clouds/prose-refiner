(function() {
  if (window.__novelWriterLoaded) return;
  window.__novelWriterLoaded = true;

  let basePath = '/static/js/novel/';
  let scripts = document.getElementsByTagName('script');
  let version = '?v=3.7';

  for (let i = 0; i < scripts.length; i++) {
    let src = scripts[i].src;
    if (src && src.indexOf('novel/novel.js') !== -1) {
      basePath = src.substring(0, src.lastIndexOf('/') + 1);
      let idx = src.indexOf('?');
      if (idx !== -1) {
        version = src.substring(idx);
      }
      break;
    }
  }

  const batchCore = [
    basePath + 'api/novel-api.js' + version,
    basePath + 'core/data.js' + version,
    basePath + 'core/charCounter.js' + version,
    basePath + 'core/attributes.js' + version,
    basePath + 'core/modal.js' + version
  ];
  const batchCrud = [
    basePath + 'crud/character.js' + version,
    basePath + 'crud/timeline.js' + version,
    basePath + 'crud/location.js' + version
  ];
  const batchPage = [
    basePath + 'page/novel-work.js' + version,
    basePath + 'page/novel-weave.js' + version,
    basePath + 'page/novel-outline.js' + version,
    basePath + 'page/novel-volume.js' + version,
    basePath + 'page/novel-chapter.js' + version,
    basePath + 'page/novel-deduction.js' + version,
    basePath + 'page/novel-content.js' + version
  ];

  function loadScript(src) {
    return new Promise(function(resolve, reject) {
      let script = document.createElement('script');
      script.src = src;
      script.onload = function() { resolve(); };
      script.onerror = function() { reject(new Error('Failed to load: ' + src)); };
      document.head.appendChild(script);
    });
  }

  function _v(path) {
    if (!version) return path;
    if (path.indexOf('?') !== -1) return path;
    return path + version;
  }

  const CACHE_KEY_NOVEL_BG = 'card_config_novel_bg';

  function setNovelBg(url) {
    const container = document.querySelector('.container');
    if (container) {
      container.style.backgroundImage = `url("${_v(url)}")`;
      container.style.backgroundSize = 'cover';
      container.style.backgroundPosition = 'center';
      container.style.backgroundRepeat = 'no-repeat';
      container.style.backgroundAttachment = 'fixed';
    }
  }

  async function loadNovelBgConfig() {
    const cachedUrl = window.AppCache?.get(CACHE_KEY_NOVEL_BG);
    if (cachedUrl) {
      setNovelBg(cachedUrl);
    }

    try {
      if (!window.__cardConfigPromise) {
        window.__cardConfigPromise = fetch('/api/card-config').then(r => r.json());
      }
      const data = await window.__cardConfigPromise;

      const novelBgUrl = data.novel_bg_image_url || `/media/image/${data.novel_bg_image_id || 1}.png`;

      window.AppCache?.set(CACHE_KEY_NOVEL_BG, novelBgUrl, 1800);
      if (cachedUrl !== novelBgUrl) {
        setNovelBg(novelBgUrl);
      }
    } catch (err) {
      console.warn('Failed to load novel background config:', err);
      if (!cachedUrl) {
        setNovelBg(`/media/image/1.png`);
      }
    }
  }

  function initDOM() {
    if (window.initWorkPage) window.initWorkPage();
    if (window.initWeavePage) window.initWeavePage();
    if (window.NovelAPI && window.NovelAPI.initSSEListener) window.NovelAPI.initSSEListener();
    if (window.setupVisibilityControl) window.setupVisibilityControl();
    if (window.initVolumePage) window.initVolumePage();
    if (window.initChapterPage) window.initChapterPage();
    if (window.initDeductionPage) window.initDeductionPage();
    if (window.initContentPage) window.initContentPage();

    loadNovelBgConfig();
  }

  async function loadAll() {
    const totalCount = batchCore.length + batchCrud.length + batchPage.length;
    try {
      await Promise.all(batchCore.map(loadScript));
      await Promise.all(batchCrud.map(loadScript));
      await Promise.all(batchPage.map(loadScript));
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDOM);
      } else {
        initDOM();
      }
      console.log('Novel Writer initialized: ' + totalCount + ' modules loaded');
    } catch (err) {
      console.error('Failed to initialize:', err);
    }
  }

  loadAll().then(_ => {});
})();