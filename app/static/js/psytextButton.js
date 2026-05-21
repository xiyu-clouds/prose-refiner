(function () {
  // 防止重复注入
  if (document.getElementById('psytext-button-styles') || document.querySelector('.button.psytext-injected')) {
    return;
  }

  // === 注入 CSS ===
  const style = document.createElement('style');
  style.id = 'psytext-button-styles';
  style.textContent = `
    /* ===== PSYTEXT 按钮（左上角）===== */
    .button.psytext-injected {
      position: absolute;
      top: 16px;
      left: 16px;
      display: flex;
      gap: 0;
      border-radius: 4px;
      overflow: hidden;
      z-index: 1000; /* 确保在最上层 */
    }

    .button.psytext-injected .box {
      width: 32px;
      height: 38px;
      display: flex;
      justify-content: center;
      align-items: center;
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      transition: all 0.8s;
      cursor: pointer;
      position: relative;
      background-color: #6a5af9;
      overflow: hidden;
    }

    .button.psytext-injected:hover .box {
      box-shadow: inset 0 0 8px rgba(255, 255, 255, 0.3);
    }

    .button.psytext-injected .box:before {
      content: "";
      position: absolute;
      top: 0;
      background: rgba(15, 15, 15, 0.6);
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      transform: translateY(100%);
      transition: transform 0.4s;
      color: white;
    }

    .button.psytext-injected .box:nth-child(1)::before { content: "P"; transform: translateY(-100%); }
    .button.psytext-injected .box:nth-child(2)::before { content: "S"; transform: translateY(100%); }
    .button.psytext-injected .box:nth-child(3)::before { content: "Y"; transform: translateY(-100%); }
    .button.psytext-injected .box:nth-child(4)::before { content: "T"; transform: translateY(100%); }
    .button.psytext-injected .box:nth-child(5)::before { content: "E"; transform: translateY(-100%); }
    .button.psytext-injected .box:nth-child(6)::before { content: "X"; transform: translateY(100%); }
    .button.psytext-injected .box:nth-child(7)::before { content: "T"; transform: translateY(-100%); }

    .button.psytext-injected:hover .box:before {
      transform: translateY(0);
    }
  `;
  document.head.appendChild(style);

  // === 创建按钮 DOM ===
  const buttonContainer = document.createElement('div');
  buttonContainer.className = 'button psytext-injected';

  const letters = ['P', 'S', 'Y', 'T', 'E', 'X', 'T'];
  letters.forEach(letter => {
    const box = document.createElement('div');
    box.className = 'box';
    box.textContent = letter;
    buttonContainer.appendChild(box);
  });

  // 等待 DOM 加载完成再插入（兼容 defer/async）
  if (document.body) {
    document.body.appendChild(buttonContainer);
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      document.body.appendChild(buttonContainer);
    });
  }
})();