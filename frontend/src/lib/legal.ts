export interface LegalDoc { title: string; sections: { heading: string; body: string }[] }

export const TERMS: LegalDoc = {
  title: 'Terms of Service',
  sections: [
    { heading: 'Experimental System', body: 'MeghSync is an advanced flood forecasting and decision-support system intended to assist with situational awareness, planning, and response coordination. Forecasts, alerts, and routing recommendations provided by the system are generated using predictive models and available environmental and infrastructure data.' },
    { heading: 'Assumption of Risk', body: 'MeghSync is intended as a decision-support tool and should not be relied upon as the sole source of information for life-safety, medical, evacuation, or other critical decisions during severe weather or flooding events. Users should always follow official advisories, emergency instructions, and guidance from relevant authorities.' },
    { heading: 'Acceptable Use', body: 'Users agree to operate MeghSync responsibly and only for legitimate forecasting, monitoring, planning, and emergency-response purposes. Any attempt to disrupt, overload, manipulate, or otherwise interfere with the system or its services may result in immediate termination of access.' },
    { heading: 'Data & Forecast Limitations', body: 'Flood forecasts, risk assessments, and recommendations may be affected by the availability, accuracy, and timeliness of input data. Users should consider system outputs alongside official information, local conditions, and professional judgment.' },
    { heading: 'Service Responsibility', body: 'MeghSync provides decision-support information and does not replace the judgment, authority, or responsibilities of designated emergency-management agencies, municipal authorities, or other authorized personnel.' },
  ],
};

export const PRIVACY: LegalDoc = {
  title: 'Privacy Policy',
  sections: [
    { heading: 'Information We Collect', body: 'MeghSync may collect user-provided information, location data, and usage information required to provide forecasting, alerts, routing, and decision-support services.' },
    { heading: 'How We Use Information', body: 'Collected information is used to operate, improve, and secure MeghSync and to provide relevant forecasts, alerts, and recommendations.' },
    { heading: 'Data Protection', body: 'We take reasonable measures to protect information from unauthorized access, misuse, or disclosure. However, no digital system can guarantee complete security.' },
    { heading: 'Data Sharing', body: 'Personal information is not shared with third parties except when required to provide services, comply with applicable law, or support authorized operations.' },
    { heading: 'Data Retention', body: 'Information is retained only as long as necessary for operational, legal, or service-related purposes.' },
    { heading: 'Updates', body: 'This policy may be updated periodically. Continued use of MeghSync indicates acceptance of the updated policy.' },
  ],
};
