export const ROBOT = `<svg viewBox="0 0 140 150" aria-hidden="true" focusable="false"><g class="bot">
  <g class="arm arm-l"><rect x="20" y="98" width="13" height="32" rx="6.5" class="arm"/></g>
  <g class="arm arm-r"><rect x="107" y="98" width="13" height="32" rx="6.5" class="arm"/><g class="lua"><path d="M113 126 L128 98" class="lua-stalk"/><ellipse cx="126" cy="99" rx="2" ry="3.8" transform="rotate(25 126 99)"/><ellipse cx="131" cy="102" rx="2" ry="3.8" transform="rotate(60 131 102)"/><ellipse cx="124" cy="104" rx="2" ry="3.8" transform="rotate(-10 124 104)"/><ellipse cx="129" cy="107" rx="2" ry="3.8" transform="rotate(55 129 107)"/><ellipse cx="122" cy="110" rx="2" ry="3.8" transform="rotate(-15 122 110)"/></g></g>
  <rect class="body-r" x="38" y="94" width="64" height="44" rx="15"/><g class="flag"><rect x="57" y="105" width="26" height="18" rx="2" fill="#da251d"/><polygon points="70.0,108.8 71.2,112.3 74.9,112.4 72.0,114.6 73.1,118.2 70.0,116.1 66.9,118.2 68.0,114.6 65.1,112.4 68.8,112.3" fill="#ffd400"/></g>
  <g class="head">
    <rect class="plate" x="30" y="46" width="80" height="56" rx="19"/><rect class="screen" x="39" y="54" width="62" height="40" rx="13"/>
    <g class="eyes"><g class="lids"><ellipse class="eye" cx="57" cy="70" rx="5.5" ry="7.5"/><ellipse class="eye" cx="83" cy="70" rx="5.5" ry="7.5"/></g></g>
    <g class="eyes-happy"><path d="M51 73 Q57 64 63 73"/><path d="M77 73 Q83 64 89 73"/></g>
    <path class="mouth smile" d="M60 82 Q70 90 80 82"/><path class="mouth m-frown" d="M60 87 Q70 80 80 87"/>
    <ellipse class="m-talk" cx="70" cy="84" rx="6" ry="2.2"/>
    <circle class="blush" cx="48" cy="82" r="3.5"/><circle class="blush" cx="92" cy="82" r="3.5"/>
    <path class="sweat" d="M104 52 q5 8 0 11 q-5 -3 0 -11z"/>
    <path class="hat" d="M70 6 L120 50 Q70 62 20 50 Z"/>
    <path class="hat-rib" d="M70 6 L48 54 M70 6 L70 57 M70 6 L92 54"/>
    <path class="strap" d="M36 55 L38 90 M104 55 L102 90"/><g class="tassel"><circle cx="38" cy="93" r="3.4"/><circle cx="102" cy="93" r="3.4"/></g>
    <circle class="tip" cx="70" cy="7" r="5"/>
  </g></g></svg>`;

import { $ } from './util.js';

export const QUIPS = ['Dạ, em chào anh/chị ạ! Em giúp anh/chị tra cứu văn bản nghiệp vụ. Anh/chị cứ hỏi nhé.',
  'Dạ, em chỉ trả lời theo tài liệu đã tải lên, và luôn kèm nguồn để anh/chị đối chiếu ạ.',
  'Dạ, nếu có nhiều văn bản sửa đổi nhau, em sẽ nêu từng văn bản kèm ngày ban hành ạ.',
  'Anh/chị cần hỏi gì về lãi suất, điều kiện hay thời hạn vay ạ?'];

const STATUS = {idle: 'Dạ, em sẵn sàng ạ', typing: 'Dạ, em đang đọc câu hỏi ạ…', think: 'Dạ, em đang tìm trong tài liệu…',
  talk: 'Em đang soạn câu trả lời ạ…', happy: 'Dạ, xong rồi ạ. Anh/chị bấm [S1] để xem nguồn.',
  oops: 'Dạ, em gặp lỗi, anh/chị xem thông báo giúp em ạ.', hello: 'Dạ, em chào anh/chị ạ'};

let timer = null;
const robots = () => document.querySelectorAll('.robot');

export function setRobot(state, revertMs) {
  robots().forEach(r => { if (!r.innerHTML.trim()) r.innerHTML = ROBOT; r.dataset.state = state; });
  const status = $('#botStatus');
  if (status) status.textContent = STATUS[state] || '';
  clearTimeout(timer);
  if (revertMs) timer = setTimeout(() => setRobot('idle'), revertMs);
}

export function trackPointer() {
  document.addEventListener('pointermove', e => {
    robots().forEach(r => {
      const b = r.getBoundingClientRect();
      if (!b.width) return;
      const dx = (e.clientX - (b.left + b.width / 2)) / innerWidth, dy = (e.clientY - (b.top + b.height / 2)) / innerHeight;
      r.style.setProperty('--ex', Math.max(-3.5, Math.min(3.5, dx * 9)).toFixed(2));
      r.style.setProperty('--ey', Math.max(-3, Math.min(3, dy * 8)).toFixed(2));
    });
  });
}
