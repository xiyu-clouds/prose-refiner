(function () {
  if (document.getElementById('psytext-footer')) return;

  const footer = document.createElement('div');
  footer.id = 'psytext-footer';
  footer.style.cssText = `
    height: 280px;
    width: 100%;
    background: url("/psytext_analyst/static/public/assets/images/4.png") no-repeat center top / cover;
    background-blend-mode: overlay;
    display: flex;
    justify-content: center;
    align-items: center; /* 垂直+水平居中核心 */
    border-radius: 10px;
    box-sizing: border-box;
    color: #fff;
    margin-top: auto;
  `;

  const overlay = document.createElement('div');
  overlay.style.cssText = `
    background-color: rgba(34, 34, 34, 0.5);
    min-width: 600px;
    max-width: 70%;
    width: fit-content;
    padding: 24px 30px;
    border-radius: 10px;
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    text-align: center;
  `;

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

  // === 备案链接（现在可点击！）===
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
  document.body.appendChild(footer);

  // 确保 body 布局支持 flex
  if (!document.body.style.display || document.body.style.display === 'block') {
    document.body.style.display = 'flex';
    document.body.style.flexDirection = 'column';
    document.body.style.minHeight = '100vh';
  }
})();