#include <cassert>
#include <iostream>
#include "components/guanjie/scanner.h"
using esphome::guanjie::Scanner;
int main() {
  const std::string id(32,'a');
  Scanner s;
  assert(!s.begin("bad",1,0x6201));
  assert(!s.begin(id,0,0x6201));
  assert(!s.begin(id,33,0x6201));
  assert(!s.begin(id,1,0x6204));
  assert(!s.begin(id,1,0x16201));
  assert(s.begin(id,1,0x6201));
  assert(!s.begin(id,2,0x6201));
  assert(!s.should_send(1000,true));
  assert(!s.should_send(1500,false));
  assert(!s.should_send(2499,false));
  assert(s.should_send(2500,false));
  assert(!s.should_send(2501,false));
  s.finish("responded",2512,1);
  assert(s.value==1 && s.latency==12);
  s.finish("timeout",2600); // Duplicate terminal callback must not change result.
  assert(s.value==1 && s.latency==12);
  assert(!s.can_resume(3511));
  assert(s.can_resume(3512));
  s.released();assert(!s.busy());
  // Timeout also resumes without any client cleanup message.
  assert(s.begin(id,32,0x6101));
  assert(!s.should_send(4000,false));
  assert(s.should_send(5000,false));
  s.finish("timeout",5700);assert(s.can_resume(6700));
  s.released();
  // millis() wraparound.
  assert(s.begin(id,1,0x6201));
  assert(!s.should_send(0xffffff00U,false));
  assert(!s.should_send(743,false));
  assert(s.should_send(744,false));
  s.finish("modbus_exception",800,0,2);
  assert(s.exception==2 && s.can_resume(1800));
  std::cout << "scanner state-machine tests PASS\n";
}
