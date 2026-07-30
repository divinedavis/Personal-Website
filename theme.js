/* Light/dark theme for divinedavis.com.
 *
 * Loaded synchronously from <head> so the saved choice is on <html> before the
 * first frame — deferring it makes every page flash white on the way to dark.
 * There are no accounts here, so the preference lives in localStorage; a first
 * visit follows the operating system, and keeps following it until the visitor
 * picks a side. */
(function () {
  var KEY = 'dd.theme';

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function systemPrefers() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }
  function current() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }
  function label(theme) {
    return theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  }
  function apply(theme, remember) {
    theme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    if (remember) { try { localStorage.setItem(KEY, theme); } catch (e) {} }
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.textContent = theme === 'dark' ? '☀ Light' : '☾ Dark';
      btn.setAttribute('aria-label', label(theme));
      btn.title = label(theme);
    }
  }

  var saved = stored();
  apply(saved === 'light' || saved === 'dark' ? saved : systemPrefers(), false);

  // Someone who hasn't chosen yet keeps tracking the OS, including a change
  // made while the page is open (macOS auto light/dark at sunset).
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onSystem = function (e) { if (!stored()) apply(e.matches ? 'dark' : 'light', false); };
    if (mq.addEventListener) mq.addEventListener('change', onSystem);
    else if (mq.addListener) mq.addListener(onSystem);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    apply(current(), false);   // stamp the button with the theme already showing
    btn.addEventListener('click', function () {
      apply(current() === 'dark' ? 'light' : 'dark', true);
    });
  });
})();
