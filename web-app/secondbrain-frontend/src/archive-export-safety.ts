/** Exported/printed HTML is inert; rich style values cannot fetch external URLs. */
export function sanitizeArchiveExportHtml(html: string) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script,iframe,object,embed,base,link,meta,form,input,button,textarea,select,foreignObject,animate,animateMotion,animateTransform,set').forEach(element => element.remove());
  doc.querySelectorAll('*').forEach(element => {
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase(), value = attribute.value.trim();
      if (name.startsWith('on') || name === 'srcdoc' || name === 'formaction') element.removeAttribute(attribute.name);
      if (['href', 'src', 'xlink:href'].includes(name) && !/^(https?:|mailto:|blob:|data:image\/(?:png|jpeg|gif|webp);base64,|#|\/|\.\/)/i.test(value)) element.removeAttribute(attribute.name);
    }
    const styled = element as HTMLElement;
    if (styled.style) for (const property of Array.from(styled.style)) {
      if (/url\s*\(|expression\s*\(|@import|-moz-binding/i.test(styled.style.getPropertyValue(property))) styled.style.removeProperty(property);
    }
  });
  return doc.body.innerHTML;
}

