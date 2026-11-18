// CloudFront Function (viewer-request)：按国家改写市场前缀 + 剥离追踪参数
var EU = ['DE','FR','NL','BE','IT','ES','IE','AT','PL','SE','DK','FI','PT'];
var TRACKING = ['live_trace_id','share_from','fbclid','ttclid','gclid'];
// 故障注入 F2：chaos 会把 STRIP_EU_TRACKING 改为 false
var STRIP_EU_TRACKING = true;

function handler(event) {
  var req = event.request;
  var h = req.headers;
  var country = h['cloudfront-viewer-country'] ? h['cloudfront-viewer-country'].value : 'SG';
  var market = EU.indexOf(country) >= 0 ? 'eu' : 'sg';

  if (req.uri.indexOf('/live/') === 0) {
    req.uri = '/' + market + req.uri.substring(5);
    if (req.uri.endsWith('/')) { req.uri += 'index.html'; }
  }
  var strip = (market === 'sg') || STRIP_EU_TRACKING;
  if (strip) {
    var qs = {};
    for (var k in req.querystring) {
      if (k.indexOf('utm_') === 0 || TRACKING.indexOf(k) >= 0) { continue; }
      qs[k] = req.querystring[k];
    }
    req.querystring = qs;
  }
  h['x-market'] = {value: market};
  return req;
}
