(function () {
  window.setLoadingMessage = function (message) {
    document.getElementById("loading-message").textContent = message;
  };

  (function () {
    const urlParams = new URLSearchParams(window.location.search);
    const msg = urlParams.get("msg");
    if (msg) {
      setLoadingMessage(decodeURIComponent(msg));
    }
  })();

  (function autoCheckHealth() {
    fetch("/api/healthz")
      .then((res) => {
        if (res.ok) {
          const urlParams = new URLSearchParams(window.location.search);
          let targetUrl = "/"; // 默认跳首页

          const redirectParam = urlParams.get("redirect");
          if (redirectParam) {
            try {
              const decoded = decodeURIComponent(redirectParam);
              // 安全检查：不能是 loading.html 自身，且必须是合法路径
              if (
                decoded &&
                decoded.startsWith("/") &&
                !decoded.includes("loading.html") &&
                decoded !== window.location.pathname
              ) {
                targetUrl = decoded;
              }
            } catch (e) {
              // 解码失败，用默认
            }
          }
          window.location.href = targetUrl;
        } else {
          setTimeout(autoCheckHealth, 1500);
        }
      })
      .catch(() => setTimeout(autoCheckHealth, 1500));
  })();
})();