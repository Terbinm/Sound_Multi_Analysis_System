/**
 * Tech Motion Engine - UI 增強工具
 * 功能：Toast 通知、表單與表格的微動態
 */

class TechMotion {
  constructor() {
    this.init();
  }

  /**
   * 初始化
   */
  init() {
    this.initToastContainer();
    console.log('TechMotion initialized');
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
 * DOM 載入後初始化增強
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

  console.log('All tech enhancements initialized');
});
