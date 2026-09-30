#include <algorithm>
#include <cassert>
#include <cstring>
#include "components/guanjie/protocol.h"
#include "components/guanjie/scanner.h"
using namespace esphome::guanjie;
int main() {
  Protocol p;
  p.valid.fill(true); p.observed.fill(15000);
  p.values[1]=1; p.values[2]=53;
  p.result="Previous control operation failed";
  p.observed[6]=0;
  p.expire(16000);
  assert(p.ready(16000));
  assert(std::strcmp(p.polling_health(16000),"Core ready; optional data unavailable")==0);
  assert(std::strcmp(p.result,"Previous control operation failed")==0);
  p.transaction={1,3,0x6101,1,p.epoch};p.in_flight=true;
  const uint8_t response[]={3,2,0,20};p.response(response,4,16001);
  assert(std::all_of(p.valid.begin(),p.valid.end(),[](bool v){return v;}));
  assert(std::strcmp(p.polling_health(16001),"All polling data fresh")==0);
  assert(std::strcmp(p.result,"Previous control operation failed")==0);
  p.observed[0]=0;p.expire(16002);
  assert(!p.ready(16002));assert(p.core_age(16002)==UINT32_MAX);
  assert(std::strcmp(p.polling_health(16002),"Core data stale or unavailable")==0);
  // Background read failures must not erase a prior control outcome either.
  p.in_flight=true;p.transaction={1,3,0x6201,1,p.epoch};p.failure(16003);
  assert(std::strcmp(p.result,"Previous control operation failed")==0);
  p.pause_for_maintenance(false);
  assert(p.maintenance && !p.ready(16004));
  assert(std::strcmp(p.result,"Previous control operation failed")==0);
  Protocol rejected;
  Write no_write{0x6201,0};
  assert(!rejected.submit(&no_write,1,1234));
  assert(rejected.result_recorded && rejected.result_uptime_ms==1234);
  rejected.expire(16000);
  assert(rejected.result_uptime_ms==1234);
  Protocol normal;
  Transaction tx;
  for (unsigned i=0;i<6;++i) {
    const uint32_t now=1000+i*200;
    assert(normal.next(now,tx));
    const uint8_t value=tx.reg==0x6202?1:tx.reg==0x6203?53:0;
    const uint8_t read[]={3,2,0,value};normal.response(read,4,now+40);
  }
  assert(normal.ready(2100));assert(normal.core_poll_seq==1);
  Scanner s;
  const std::string id(32,'a');const uint32_t start=UINT32_MAX-500;
  assert(s.begin(id,1,0x6201,start));
  assert(!s.expired(start+9999));assert(s.expired(start+10000));
  s.abort(start+10000);assert(!s.can_resume(start+10999));assert(s.can_resume(start+11000));
  assert(std::strcmp(s.outcome,"gateway_error")==0);
  assert(!s.begin(id,1,0x6201,start+11000));s.released();
  assert(s.begin(id,1,0x6201,start+11001));
}
