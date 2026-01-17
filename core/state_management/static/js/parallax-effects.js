/**
 * Tech Motion Engine - 視差與進場動畫整合
 * 功能：滑鼠視差、進場淡入、表單與表格的微動態，避免 transform/opacity 互相覆蓋
 */

class TechMotion {
  constructor() {
    this.levels = {
      layer1: 0.04,
      layer2: 0.08,
      layer3: 0.14
    };

    this.targets = new Set();
    this.mouseX = window.innerWidth / 2;
    this.mouseY = window.innerHeight / 2;
    this.windowWidth = window.innerWidth;
    this.windowHeight = window.innerHeight;
    this.isDesktop = this.windowWidth > 768;
    this.rafId = null;
    this.onMouseMove = null;

    this.intersectionObserver = null;
    this.mutationObserver = null;

    this.handleResize = this.handleResize.bind(this);
    this.handleMouseMove = this.handleMouseMove.bind(this);

    this.init();
  }

  /**
   * 初始化與元素收集
   */
  init() {
    this.collectTargets();
    this.setupScrollObserver();
    this.bindEvents();
    this.initToastContainer();
    console.log('TechMotion initialized');
  }

  /**
   * 收集需要套用效果的元素
   */
  collectTargets() {
    const selectors = [
      { selector: '.tech-card', level: 'layer2' },
      { selector: '.tech-card-sm', level: 'layer2' },
      { selector: '.parallax-float', level: 'layer3' }
    ];

    selectors.forEach(({ selector, level }) => {
      document.querySelectorAll(selector).forEach(el => this.prepareElement(el, level));
    });
  }

  /**
   * 初始化單一元素
   */
  prepareElement(el, level) {
    if (!el || el.dataset.motionInit === 'true') return;

    el.dataset.motionInit = 'true';
    el.dataset.parallaxLevel = level;
    el.style.setProperty('--parallax-x', el.style.getPropertyValue('--parallax-x') || '0px');
    el.style.setProperty('--parallax-y', el.style.getPropertyValue('--parallax-y') || '0px');
    el.classList.add('parallax-layer', `parallax-${level}`, 'tech-animate-ready');

    this.targets.add(el);

    if (this.intersectionObserver) {
      this.intersectionObserver.observe(el);
    }
  }

  /**
   * 進場動畫觀察器
   */
  setupScrollObserver() {
    this.intersectionObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('tech-animate-in');
          entry.target.classList.remove('tech-animate-ready');
          this.intersectionObserver.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.2,
      rootMargin: '0px 0px -10% 0px'
    });

    this.targets.forEach(el => this.intersectionObserver.observe(el));
  }

  /**
   * 綁定事件：滑鼠移動、視窗縮放、DOM 變化
   */
  bindEvents() {
    this.enableParallaxIfDesktop();

    window.addEventListener('resize', this.throttle(this.handleResize, 150));

    this.mutationObserver = new MutationObserver(this.throttle(() => {
      this.collectTargets();
    }, 200));

    this.mutationObserver.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  /**
   * 啟用桌面版視差
   */
  enableParallaxIfDesktop(forceRebind = false) {
    if (!this.isDesktop) return;

    if (!this.onMouseMove || forceRebind) {
      if (this.onMouseMove) {
        document.removeEventListener('mousemove', this.onMouseMove);
      }
      this.onMouseMove = this.throttle(this.handleMouseMove, 16);
      document.addEventListener('mousemove', this.onMouseMove);
    }
  }

  /**
   * 視窗尺寸變化
   */
  handleResize() {
    const wasDesktop = this.isDesktop;
    this.windowWidth = window.innerWidth;
    this.windowHeight = window.innerHeight;
    this.isDesktop = this.windowWidth > 768;

    if (!this.isDesktop) {
      this.disableParallax();
      this.resetParallaxOffsets();
    } else if (!wasDesktop && this.isDesktop) {
      this.enableParallaxIfDesktop(true);
    }
  }

  /**
   * 滑鼠移動
   */
  handleMouseMove(e) {
    this.mouseX = e.clientX;
    this.mouseY = e.clientY;

    if (!this.rafId) {
      this.rafId = requestAnimationFrame(() => {
        this.applyParallaxOffsets();
        this.rafId = null;
      });
    }
  }

  /**
   * 套用視差位移到所有目標
   */
  applyParallaxOffsets() {
    if (!this.isDesktop || this.targets.size === 0) return;

    const xPercent = (this.mouseX / this.windowWidth - 0.5) * 2;
    const yPercent = (this.mouseY / this.windowHeight - 0.5) * 2;

    this.targets.forEach(el => {
      const layerKey = el.dataset.parallaxLevel || 'layer2';
      const offset = this.levels[layerKey] ?? this.levels.layer2;
      el.style.setProperty('--parallax-x', `${xPercent * offset * 100}px`);
      el.style.setProperty('--parallax-y', `${yPercent * offset * 100}px`);
    });
  }

  /**
   * 清空位移，給停用視差或改為行動裝置時使用
   */
  resetParallaxOffsets() {
    this.targets.forEach(el => {
      el.style.setProperty('--parallax-x', '0px');
      el.style.setProperty('--parallax-y', '0px');
    });
  }

  /**
   * 停用桌面視差
   */
  disableParallax() {
    if (this.onMouseMove) {
      document.removeEventListener('mousemove', this.onMouseMove);
      this.onMouseMove = null;
    }
  }

  /**
   * 初始化 Toast 容器
   */
  initToastContainer() {
    if (!document.getElementById('toast-container')) {
      const container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
      document.body.appendChild(container);
    }
  }

  /**
   * 顯示 Toast
   */
  showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'tech-toast';

    const icons = {
      success: '<i class="fas fa-check-circle" style="color: #22c55e;"></i>',
      error: '<i class="fas fa-exclamation-circle" style="color: #ef4444;"></i>',
      warning: '<i class="fas fa-exclamation-triangle" style="color: #f59e0b;"></i>',
      info: '<i class="fas fa-info-circle" style="color: #3b82f6;"></i>'
    };

    toast.innerHTML = `
      ${icons[type] || icons.info}
      <span style="flex: 1;">${message}</span>
      <button onclick="this.parentElement.remove()" style="background: none; border: none; color: #9ca3af; cursor: pointer; padding: 4px; transition: color 0.2s;">
        <i class="fas fa-times"></i>
      </button>
    `;

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
      }, duration);
    }
  }

  /**
   * 節流
   */
  throttle(func, delay) {
    let lastCall = 0;
    return (...args) => {
      const now = Date.now();
      if (now - lastCall >= delay) {
        lastCall = now;
        func.apply(this, args);
      }
    };
  }
}

/**
 * 動態數字計數器
 */
class CounterAnimator {
  static animateCounter(element, targetValue, duration = 1000) {
    const startValue = parseInt(element.textContent) || 0;
    const increment = (targetValue - startValue) / (duration / 16);
    let currentValue = startValue;

    element.classList.add('tech-counter', 'updating');

    const updateCounter = () => {
      currentValue += increment;
      if ((increment > 0 && currentValue >= targetValue) ||
          (increment < 0 && currentValue <= targetValue)) {
        element.textContent = targetValue;
        element.classList.remove('updating');
        return;
      }
      element.textContent = Math.floor(currentValue);
      requestAnimationFrame(updateCounter);
    };

    requestAnimationFrame(updateCounter);
  }

  static batchUpdate(updates) {
    Object.entries(updates).forEach(([elementId, targetValue]) => {
      const element = document.getElementById(elementId);
      if (element) {
        this.animateCounter(element, targetValue);
      }
    });
  }
}

/**
 * 表格增強器
 */
class TableEnhancer {
  static enhance(tableSelector = 'table') {
    document.querySelectorAll(tableSelector).forEach(table => {
      if (!table.classList.contains('tech-table')) {
        table.classList.add('tech-table');
      }

      table.querySelectorAll('tbody tr').forEach(row => {
        row.addEventListener('mouseenter', function() {
          this.style.position = 'relative';
          this.style.zIndex = '1';
        });

        row.addEventListener('mouseleave', function() {
          this.style.position = '';
          this.style.zIndex = '';
        });
      });
    });
  }

  static addSorting(table) {
    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
      header.style.cursor = 'pointer';
      header.style.userSelect = 'none';

      header.addEventListener('click', () => {
        this.sortTable(table, index);
      });
    });
  }

  static sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isAscending = table.dataset.sortOrder !== 'asc';

    rows.sort((a, b) => {
      const aText = a.cells[columnIndex].textContent.trim();
      const bText = b.cells[columnIndex].textContent.trim();

      const aNum = parseFloat(aText);
      const bNum = parseFloat(bText);

      if (!isNaN(aNum) && !isNaN(bNum)) {
        return isAscending ? aNum - bNum : bNum - aNum;
      }

      return isAscending ? aText.localeCompare(bText) : bText.localeCompare(aText);
    });

    rows.forEach(row => tbody.appendChild(row));
    table.dataset.sortOrder = isAscending ? 'asc' : 'desc';
  }
}

/**
 * 表單增強器
 */
class FormEnhancer {
  static enhance() {
    document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], input[type="number"], textarea, select').forEach(input => {
      if (!input.classList.contains('tech-input')) {
        input.classList.add('tech-input');
      }

      input.addEventListener('focus', function() {
        this.parentElement?.classList.add('focused');
      });

      input.addEventListener('blur', function() {
        this.parentElement?.classList.remove('focused');
      });
    });

    document.querySelectorAll('button, input[type="submit"], a.btn').forEach(button => {
      if (!button.classList.contains('tech-button') &&
          !button.classList.contains('no-enhance')) {
        button.classList.add('tech-button');
      }
    });
  }

  static addLoadingState(form, submitButton) {
    form.addEventListener('submit', function() {
      submitButton.disabled = true;
      submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 處理中...';
    });
  }
}

/**
 * 載入狀態管理器
 */
class LoadingManager {
  static show(element, loadingHTML = '<div class="flex justify-center p-8"><div class="tech-spinner tech-spinner-glow"></div></div>') {
    element.dataset.originalContent = element.innerHTML;
    element.innerHTML = loadingHTML;
  }

  static hide(element, newContent = null) {
    if (newContent !== null) {
      element.innerHTML = newContent;
    } else if (element.dataset.originalContent) {
      element.innerHTML = element.dataset.originalContent;
      delete element.dataset.originalContent;
    }
  }

  static createSkeleton(rows = 3) {
    let html = '<div class="space-y-3">';
    for (let i = 0; i < rows; i++) {
      html += `
        <div class="tech-skeleton h-4" style="width: ${80 + Math.random() * 20}%"></div>
      `;
    }
    html += '</div>';
    return html;
  }
}

// 全局instance
let techMotion;

/**
 * DOM 載入後初始化動畫與增強
 */
document.addEventListener('DOMContentLoaded', function() {
  techMotion = new TechMotion();

  TableEnhancer.enhance();
  FormEnhancer.enhance();

  // 向外暴露工具
  window.techMotion = techMotion;
  window.parallaxController = techMotion;
  window.ParallaxController = TechMotion;
  window.ScrollAnimator = TechMotion;
  window.CounterAnimator = CounterAnimator;
  window.TableEnhancer = TableEnhancer;
  window.FormEnhancer = FormEnhancer;
  window.LoadingManager = LoadingManager;

  window.showToast = (message, type, duration) => {
    techMotion?.showToast(message, type, duration);
  };

  // 透過 meta tag 從後端傳遞配置，控制是否替換 alert 為 toast
  const useToastForAlerts = document.querySelector('meta[name="use-toast-alerts"]')?.content === 'true';

  if (useToastForAlerts) {
    const originalAlert = window.alert;
    window.alert = function(message) {
      if (techMotion) {
        techMotion.showToast(message, 'info', 5000);
      } else {
        originalAlert(message);
      }
    };
  }

  console.log('All tech enhancements initialized ✨');
});

/**
 * 頁面完全載入後再跑一次收集，確保動態節點也有動畫
 */
window.addEventListener('load', function() {
  if (techMotion) {
    techMotion.collectTargets();
  }
});
