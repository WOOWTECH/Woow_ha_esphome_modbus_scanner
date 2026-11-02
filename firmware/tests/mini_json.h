// Minimal JSON reader for host tests only: enough to load the bridge contract file and
// to parse the firmware's own result/info output. Not used on the device.
#pragma once

#include <cctype>
#include <cstdint>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace mini_json {

struct Value {
  enum class Type { NUL, BOOL, NUMBER, STRING, ARRAY, OBJECT } type{Type::NUL};
  bool boolean{false};
  double number{0};
  std::string string;
  std::vector<Value> array;
  std::map<std::string, Value> object;

  bool is_object() const { return type == Type::OBJECT; }
  bool is_array() const { return type == Type::ARRAY; }
  bool is_string() const { return type == Type::STRING; }
  bool is_number() const { return type == Type::NUMBER; }
  bool has(const std::string &key) const { return is_object() && object.count(key) != 0; }
  const Value &operator[](const std::string &key) const {
    auto it = object.find(key);
    if (type != Type::OBJECT || it == object.end())
      throw std::runtime_error("missing JSON key: " + key);
    return it->second;
  }
  const Value &operator[](size_t index) const { return array.at(index); }
  int64_t integer() const {
    if (type != Type::NUMBER || number != static_cast<double>(static_cast<int64_t>(number)))
      throw std::runtime_error("JSON value is not an integer");
    return static_cast<int64_t>(number);
  }
  const std::string &str() const {
    if (type != Type::STRING)
      throw std::runtime_error("JSON value is not a string");
    return string;
  }
};

class Parser {
 public:
  explicit Parser(const std::string &text) : text_(text) {}
  Value parse() {
    Value value = parse_value();
    skip_ws();
    if (pos_ != text_.size())
      fail("trailing characters");
    return value;
  }

 private:
  [[noreturn]] void fail(const char *what) {
    throw std::runtime_error(std::string("JSON parse error: ") + what + " at " + std::to_string(pos_));
  }
  void skip_ws() {
    while (pos_ < text_.size() && std::isspace(static_cast<unsigned char>(text_[pos_])))
      pos_++;
  }
  char peek() {
    skip_ws();
    if (pos_ >= text_.size())
      fail("unexpected end");
    return text_[pos_];
  }
  void expect(char c) {
    if (peek() != c)
      fail("unexpected character");
    pos_++;
  }
  bool consume(const char *word) {
    size_t n = std::char_traits<char>::length(word);
    if (text_.compare(pos_, n, word) != 0)
      return false;
    pos_ += n;
    return true;
  }
  Value parse_value() {
    Value v;
    char c = peek();
    if (c == '{') {
      v.type = Value::Type::OBJECT;
      pos_++;
      if (peek() == '}') {
        pos_++;
        return v;
      }
      while (true) {
        std::string key = parse_string();
        expect(':');
        v.object[key] = parse_value();
        if (peek() == ',') {
          pos_++;
          continue;
        }
        expect('}');
        return v;
      }
    }
    if (c == '[') {
      v.type = Value::Type::ARRAY;
      pos_++;
      if (peek() == ']') {
        pos_++;
        return v;
      }
      while (true) {
        v.array.push_back(parse_value());
        if (peek() == ',') {
          pos_++;
          continue;
        }
        expect(']');
        return v;
      }
    }
    if (c == '"') {
      v.type = Value::Type::STRING;
      v.string = parse_string();
      return v;
    }
    if (consume("true")) {
      v.type = Value::Type::BOOL;
      v.boolean = true;
      return v;
    }
    if (consume("false")) {
      v.type = Value::Type::BOOL;
      return v;
    }
    if (consume("null"))
      return v;
    size_t start = pos_;
    while (pos_ < text_.size() && (std::isdigit(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == '-' ||
                                   text_[pos_] == '+' || text_[pos_] == '.' || text_[pos_] == 'e' || text_[pos_] == 'E'))
      pos_++;
    if (start == pos_)
      fail("unexpected token");
    v.type = Value::Type::NUMBER;
    v.number = std::stod(text_.substr(start, pos_ - start));
    return v;
  }
  std::string parse_string() {
    expect('"');
    std::string out;
    while (true) {
      if (pos_ >= text_.size())
        fail("unterminated string");
      char c = text_[pos_++];
      if (c == '"')
        return out;
      if (static_cast<unsigned char>(c) < 0x20)
        fail("raw control character in string");
      if (c != '\\') {
        out += c;
        continue;
      }
      char e = text_[pos_++];
      switch (e) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
          unsigned code = std::stoul(text_.substr(pos_, 4), nullptr, 16);
          pos_ += 4;
          if (code < 0x80) {
            out += static_cast<char>(code);
          } else if (code < 0x800) {
            out += static_cast<char>(0xC0 | (code >> 6));
            out += static_cast<char>(0x80 | (code & 0x3F));
          } else {
            out += static_cast<char>(0xE0 | (code >> 12));
            out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (code & 0x3F));
          }
          break;
        }
        default: fail("bad escape");
      }
    }
  }

  const std::string &text_;
  size_t pos_{0};
};

inline Value parse(const std::string &text) { return Parser(text).parse(); }

}  // namespace mini_json
