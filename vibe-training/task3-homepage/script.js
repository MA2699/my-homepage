// 个人主页交互脚本 - 原生 JavaScript
// 仅负责移动端菜单切换，锚点跳转由 CSS scroll-behavior: smooth 原生支持

(function () {
  'use strict';

  var toggle = document.querySelector('.nav-toggle');
  var links = document.querySelector('.nav-links');

  if (!toggle || !links) {
    return;
  }

  // 切换移动端菜单展开 / 收起
  function toggleMenu(forceClose) {
    var open = forceClose ? false : !links.classList.contains('is-open');
    links.classList.toggle('is-open', open);
    toggle.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  // 点击汉堡按钮
  toggle.addEventListener('click', function () {
    toggleMenu();
  });

  // 点击任意导航链接后自动收起菜单
  links.addEventListener('click', function (e) {
    if (e.target.tagName === 'A') {
      toggleMenu(true);
    }
  });

  // 点击页面其余区域收起菜单
  document.addEventListener('click', function (e) {
    if (!links.contains(e.target) && !toggle.contains(e.target)) {
      toggleMenu(true);
    }
  });

  // 窗口放大到桌面尺寸时复位移动端菜单状态
  window.addEventListener('resize', function () {
    if (window.innerWidth > 640) {
      toggleMenu(true);
    }
  });
})();
