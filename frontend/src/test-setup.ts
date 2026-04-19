import '@testing-library/jest-dom';

if (!(HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView) {
  (HTMLElement.prototype as { scrollIntoView: () => void }).scrollIntoView =
    () => {};
}
