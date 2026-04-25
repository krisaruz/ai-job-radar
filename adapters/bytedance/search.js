/* @meta
{
  "name": "bytedance/search",
  "description": "搜索字节跳动社招岗位 (jobs.bytedance.com)",
  "domain": "jobs.bytedance.com",
  "args": {
    "keyword": {"required": true, "description": "搜索关键词 (如 AI测试, 大模型评测)"},
    "limit": {"required": false, "description": "每页数量 (默认 50)"},
    "offset": {"required": false, "description": "偏移量 (默认 0)"}
  },
  "readOnly": true,
  "example": "bb-browser site bytedance/search \"AI测试\""
}
*/

async function(args) {
  if (!args.keyword) return {error: 'Missing argument: keyword'};
  const limit = parseInt(args.limit) || 50;
  const offset = parseInt(args.offset) || 0;

  // Strategy 1: POST /api/v1/search/job/posts (confirmed 2026-04-25)
  try {
    const resp = await fetch('/api/v1/search/job/posts?' +
      'keyword=' + encodeURIComponent(args.keyword) +
      '&limit=' + limit + '&offset=' + offset, {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        keyword: args.keyword,
        limit: limit,
        offset: offset,
        job_category_id_list: [],
        tag_id_list: [],
        location_code_list: [],
        subject_id_list: [],
        recruitment_id_list: [],
        portal_type: 2,
        job_function_id_list: [],
        store_id_list: [],
      }),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if (data.code === 0 && data.data && Array.isArray(data.data.job_post_list)) {
      const total = data.data.count || 0;
      const jobs = data.data.job_post_list.map(function(p) {
        var city = '';
        if (p.city_info && p.city_info.name) city = p.city_info.name;
        else if (Array.isArray(p.city_list) && p.city_list.length > 0) city = p.city_list.map(function(c){return c.name||'';}).join(',');

        var dept = '';
        if (p.job_category && p.job_category.parent) dept = p.job_category.parent.name + ' - ' + p.job_category.name;
        else if (p.job_category) dept = p.job_category.name || '';

        return {
          jobId: String(p.id || ''),
          jobCode: p.code || '',
          title: p.title || '',
          department: dept,
          city: city,
          description: p.description || '',
          requirements: p.requirement || '',
          address: (p.job_post_info && p.job_post_info.address) || '',
          recruitType: (p.recruit_type && p.recruit_type.parent && p.recruit_type.parent.name) || '',
          publishTime: p.publish_time || 0,
          url: p.id ? 'https://jobs.bytedance.com/experienced/position/' + p.id + '/detail' : '',
        };
      });
      return {keyword: args.keyword, offset: offset, limit: limit, total: total, count: jobs.length, jobs: jobs};
    }
  } catch(e) { /* fall through to strategy 2 */ }

  // Strategy 2: Extract from rendered DOM (fallback)
  try {
    var links = document.querySelectorAll('a[href*="/position/"]');
    var jobs = [];
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var href = a.getAttribute('href') || '';
      var m = href.match(/\/experienced\/position\/(\w+)/);
      if (!m) continue;
      var pid = m[1];
      var allSpans = a.querySelectorAll('span');
      var title = '';
      for (var s = 0; s < allSpans.length; s++) {
        var txt = allSpans[s].textContent.trim();
        if (txt.length > 3) { title = txt; break; }
      }
      if (title) {
        jobs.push({
          jobId: pid, title: title,
          url: 'https://jobs.bytedance.com/experienced/position/' + pid + '/detail',
        });
      }
    }
    if (jobs.length > 0) {
      return {keyword: args.keyword, source: 'dom', count: jobs.length, jobs: jobs};
    }
  } catch(e) { /* continue */ }

  return {
    error: 'Could not find job data',
    hint: 'Open jobs.bytedance.com and search for a keyword, then inspect Network tab to verify the API endpoint.',
    keyword: args.keyword,
  };
}
