(function () {
  const container = document.getElementById('global-footer');
  if (!container) return;

  // 避免重复注入
  if (container.children.length > 0) return;

  // 创建 footer 主结构
  const footer = document.createElement('div');
  footer.id = 'psytext-footer';
  footer.style.cssText = `
    position: relative;
    height: 280px;
    width: 100%;
    background: url("/static/images/166.png") no-repeat center top / cover;
    background-blend-mode: overlay;
    border-radius: 10px;
    box-sizing: border-box;
    color: #fff;
    overflow: hidden;
  `;

  // 半透明遮罩层
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    min-width: 600px;
    max-width: 70%;
    width: fit-content;
    background-color: rgba(34, 34, 34, 0.5);
    border-radius: 10px 0 0 10px;
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 24px 30px;
    box-sizing: border-box;
    text-align: center;
  `;

  // 文字行
  const lines = [
    '© 郗彧 - 应物不留痕',
    '一蓑烟雨平江，日暮沧波起',
    '离愁碾作檐下雨，砚池墨涸犹待续',
    '温一壶杏花微雨入喉，坐拥青山听笙歌'
  ];

  lines.forEach(text => {
    const p = document.createElement('p');
    p.textContent = text;
    p.style.cssText = `
      margin: 10px 0;
      text-shadow: 0 1px 1px rgba(0,0,0,0.3), 0 2px 3px rgba(0,0,0,0.4), 0 0 6px rgba(0,0,0,0.2);
      line-height: 1.5;
      font-size: 16px;
    `;
    overlay.appendChild(p);
  });

  // 备案链接
  const beianLink = document.createElement('a');
  beianLink.href = 'https://beian.miit.gov.cn/';
  beianLink.target = '_blank';
  beianLink.textContent = '苏ICP备00000000号(测试显示用)';
  beianLink.style.cssText = `
    color: #a0d9ff;
    text-decoration: underline;
    text-shadow: 0 1px 1px rgba(0,0,0,0.3), 0 2px 3px rgba(0,0,0,0.4);
    cursor: pointer;
  `;

  beianLink.onmouseenter = () => {
    beianLink.style.color = '#ffffff';
    beianLink.style.textShadow = '0 1px 2px rgba(0,0,0,0.6)';
  };
  beianLink.onmouseleave = () => {
    beianLink.style.color = '#a0d9ff';
    beianLink.style.textShadow = '0 1px 1px rgba(0,0,0,0.3), 0 2px 3px rgba(0,0,0,0.4)';
  };

  const beianP = document.createElement('p');
  beianP.appendChild(beianLink);
  beianP.style.margin = '12px 0';
  overlay.appendChild(beianP);

  footer.appendChild(overlay);
  container.appendChild(footer);
})();