function rendreListe(elements) {
  return '<ul>' + elements.map((e) => '<li>' + e.nom + '</li>').join('') + '</ul>';
}
module.exports = { rendreListe };
