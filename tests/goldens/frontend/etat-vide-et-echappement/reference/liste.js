const ECHAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const echapper = (s) => String(s).replace(/[&<>"']/g, (c) => ECHAP[c]);

function rendreListe(elements) {
  if (!elements.length) {
    return '<div class="vide"><p>Aucune alerte pour le moment. Créez-en une pour être prévenu quand un prix bouge.</p>'
      + '<button class="action" type="button">Créer une alerte</button></div>';
  }
  return '<ul>' + elements.map((e) => '<li>' + echapper(e.nom) + '</li>').join('') + '</ul>';
}
module.exports = { rendreListe };
