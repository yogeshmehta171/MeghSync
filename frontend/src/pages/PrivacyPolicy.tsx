import React from 'react';
import { LegalBody } from '../components/LegalModal';
import { PRIVACY } from '../lib/legal';

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-slate-50 pt-24 pb-12 px-6">
      <div className="max-w-4xl mx-auto bg-white rounded-2xl shadow-sm border border-slate-200 p-8 md:p-12">
        <h1 className="text-3xl font-extrabold text-slate-800 mb-6">{PRIVACY.title}</h1>
        <LegalBody doc={PRIVACY} />
      </div>
    </div>
  );
}
