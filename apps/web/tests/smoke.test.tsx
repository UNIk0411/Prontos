import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect } from 'vitest';
import Home from '../app/page';

describe('home page smoke test', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('renders the sign-in screen when no session exists', () => {
    const markup = renderToStaticMarkup(createElement(Home));
    expect(markup).toContain('Secure operator portal');
    expect(markup).toContain('Sign in');
    expect(markup).toContain('Email');
  });
});
